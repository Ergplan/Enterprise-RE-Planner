"""Recognition of the DISCOM, state and open-access arrangement from a stored billx result, the state
settlement rules the next stage applies, and the arrangement carried into the site intake."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.db.base import session_scope
from ergplan.db.models import Bill, Connection
from ergplan.intake import bills as bill_store
from ergplan.intake import defaults, site_intake
from ergplan.platform.app import app
from tests.engine.helpers import restore_committed
from tests.intake.helpers import FakeBillx, result
from tests.platform.test_api_bill_reading import _fo, oa_result

client = TestClient(app)


@pytest.fixture
def billx(monkeypatch: pytest.MonkeyPatch) -> FakeBillx:
    fake = FakeBillx()
    monkeypatch.setattr(bill_store, "BillxClient", fake.client)
    return fake


def _upload(fake: FakeBillx, tag: str, res: dict[str, Any]) -> list[dict[str, Any]]:
    data = fake.register(tag, res)
    r = client.post("/bills", files={"file": (f"{tag}.pdf", data, "application/pdf")})
    assert r.status_code == 201, r.text
    return list(r.json())


def _recognition(bill_id: str) -> dict[str, Any]:
    r = client.get(f"/bills/{bill_id}/plan-inputs")
    assert r.status_code == 200, r.text
    return dict(r.json()["recognition"])


@pytest.mark.parametrize(
    "printed,discom",
    [
        ("PASHCHIMANCHAL VIDYUT VITRAN NIGAM LIMITED", "pvvnl"),
        ("DAKSHINANCHAL VIDYUT VITRAN NIGAM LIMITED A/D", "dvvnl"),
        ("SOUTHERN POWER DISTRIBUTION COMPANY OF TG LIMITED", "tgspdcl"),
        ("Southern Power Distribution Company of A.P. Ltd.", "apspdcl"),
        ("TAMILNADU GENERATION AND DISTRIBUTION CORPORATION", "tnpdcl"),
        ("HIMACHAL PRADESH STATE ELECTRICITY BOARD LIMITED", "hpsebl"),
        ("ASSAM POWER DISTRIBUTION COMPANY LIMITED", "apdcl"),
        ("Gulbarga Electricity Supply Company Limited", "gescom"),
        ("AN ENGINEERING WORKS", None),
        (None, None),
    ],
)
def test_a_discom_from_its_printed_name(printed: str | None, discom: str | None) -> None:
    assert defaults.discom_from_name(printed) == discom
    if discom:
        assert defaults.state_of(discom) is not None


def test_an_open_access_bill_names_its_state_rules(billx: FakeBillx) -> None:
    restore_committed()
    [b, _] = _upload(billx, "rec-oa", oa_result())
    r = _recognition(b["id"])
    assert (r["discom"], r["state"], r["state_name"]) == ("pvvnl", "UP", "Uttar Pradesh")
    assert "layout profile" in r["discom_how"]
    assert r["open_access"] == "open_access" and r["open_access_kinds"] == []
    slot = next(e for e in r["evidence"] if "time-of-day slot" in e["finding"])
    assert slot["ref"]["kind"] == "bill" and slot["ref"]["field_path"] == "energy.tod.0.open_access"
    assert any("captive, group captive or third party" in n for n in r["notes"])
    captive = next(x for x in r["settlement"] if x["ownership"] == "captive")
    assert captive["rule_label"] and "UPERC" in (captive["rulebook"] or "")
    assert captive["ref"]["kind"] in ("regulation", "order") and captive["ref"]["rule_id"]


def test_a_bill_without_a_profile_is_recognised_by_the_printed_name(
    billx: FakeBillx, jurisdictions: None
) -> None:
    res = copy.deepcopy(result("pvvnl_passed"))
    bill = res["bills"][0]
    bill["profile"] = {"id": None, "version": None, "status": "none"}
    bill["fields"]["utility"]["name"] = _fo("HIMACHAL PRADESH STATE ELECTRICITY BOARD LIMITED", page=1)
    [b] = _upload(billx, "rec-hp", res)
    r = _recognition(b["id"])
    assert (r["discom"], r["state"]) == ("hpsebl", "HP")
    assert r["discom_ref"]["field_path"] == "utility.name" and r["discom_ref"]["page"] == 1
    assert r["open_access"] == "none_seen" and r["evidence"] == []
    assert all(x["rule_label"] is None for x in r["settlement"])
    assert any("No approved settlement rules for Himachal Pradesh" in n for n in r["notes"])


def test_the_named_kind_reaches_the_intake_and_the_connection(billx: FakeBillx) -> None:
    res = copy.deepcopy(result("pvvnl_passed"))
    bill = res["bills"][0]
    bill["elements"] = [
        {
            "index": 0,
            "label": "Wheeling Charges (Group Captive)",
            "code": "wheeling_charge",
            "kind": "item",
            "stage": "current",
            "amount": _fo("1250.00", page=2),
        }
    ]
    [b] = _upload(billx, "rec-gc", res)
    r = _recognition(b["id"])
    assert r["open_access"] == "open_access" and r["open_access_kinds"] == ["group_captive"]
    assert r["evidence"][0]["ref"]["field_path"] == "elements[0].amount"
    with session_scope(actor="t") as s:
        intake = site_intake.from_bills(s, [b["id"]])
        assert intake.open_access is not None
        assert (intake.open_access.value, intake.open_access.provenance) == ("group_captive", "bill")
        assert intake.open_access.ref is not None and intake.open_access.ref.page == 2
        ids = site_intake.build(s, intake, actor="t")
        conn = s.get(Connection, ids["connection_id"])
        assert conn is not None and site_intake.recorded_ownership(conn) == "group_captive"
        assert s.get(Bill, b["id"]) is not None


def test_a_stated_arrangement_must_be_a_known_one(billx: FakeBillx) -> None:
    [b] = _upload(billx, "rec-st", copy.deepcopy(result("pvvnl_passed")))
    with session_scope(actor="t") as s:
        assert site_intake.from_bills(s, [b["id"]], {"open_access": "third_party"}).open_access.value == (  # type: ignore[union-attr]
            "third_party"
        )
        with pytest.raises(ValueError):
            site_intake.from_bills(s, [b["id"]], {"open_access": "barter"})


def test_a_charge_on_exchange_units_is_open_access_and_the_word_alone_is_not(billx: FakeBillx) -> None:
    def with_line(label: str, amount: str) -> dict[str, Any]:
        res = copy.deepcopy(result("pvvnl_passed"))
        res["bills"][0]["elements"] = [
            {
                "index": 0,
                "label": label,
                "code": "other",
                "kind": "item",
                "stage": "current",
                "amount": _fo(amount),
            }
        ]
        return res

    [charged] = _upload(billx, "rec-iex", with_line("E Tax on consumption from IEX", "512.00"))
    r = _recognition(charged["id"])
    assert r["open_access"] == "open_access" and r["open_access_kinds"] == ["exchange"]
    [zero] = _upload(billx, "rec-iex0", with_line("E Tax on consumption from IEX", "0.00"))
    assert _recognition(zero["id"])["open_access"] == "none_seen"


def test_a_bill_printing_two_tod_schemes_gives_one() -> None:
    from decimal import Decimal

    from ergplan.intake.site_intake import Fact, TodEnergy, one_scheme

    def t(name: str, a: str, b: str, kvah: str) -> TodEnergy:
        return TodEnergy(start=a, end=b, energy=Fact(value=Decimal(kvah)), slot=name)

    old = [
        t("TOD-1", "05:00", "11:00", "60"),
        t("TOD-2", "11:00", "17:00", "90"),
        t("TOD-3", "17:00", "23:00", "80"),
    ]
    new = [
        t("TOD-5", "05:00", "10:00", "50"),
        t("TOD-6", "10:00", "19:00", "130"),
        t("TOD-7", "19:00", "03:00", "90"),
        t("TOD-8", "03:00", "05:00", "20"),
    ]
    # the old scheme lost a slot in reading (23-05): only the new one covers the day
    assert [x.slot for x in one_scheme(old + new, Decimal(290), set())] == [
        "TOD-5",
        "TOD-6",
        "TOD-7",
        "TOD-8",
    ]
    whole = [*old, t("TOD-4", "23:00", "05:00", "60")]
    # both cover the day: the approved windows decide
    assert one_scheme(whole + new, Decimal(290), {("05:00", "11:00"), ("23:00", "05:00")})[0].slot == "TOD-1"
    assert one_scheme(old, Decimal(10), set()) == []
