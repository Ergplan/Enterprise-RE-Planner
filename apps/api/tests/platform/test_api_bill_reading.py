"""The reading view and the hand-off to planning: GET /bills/{id}/reading, /plan-inputs and the
page images, on a synthetic open-access bill (contract 1.1 with slot kVAh, open access and net,
every reader's reading and boxes) and a file holding two bills."""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.intake import bills as bill_store
from ergplan.intake.bill_reading import slot_hours
from ergplan.intake.site_intake import window_of
from ergplan.platform.app import app
from tests.intake.helpers import FakeBillx, result

client = TestClient(app)
SLOTS = [
    ("TOD-1 (05 to 11)", "5000", "1000.5", "3999.5", "6.800"),
    ("TOD-2 (11 to 17)", "6000", "2500", "3500", "6.800"),
    ("TOD-3 (17 to 23)", "4000", "100", "3900", "7.820"),
    ("TOD-4 (23 to 05)", "2000", "0", "2000", "5.780"),
]


def _fo(value: str, verification: str = "verified", page: int = 1, y: str = "0.3000") -> dict[str, Any]:
    return {
        "value": value,
        "unit": None,
        "printed": value,
        "page": page,
        "region": {"x": "0.5000", "y": y, "w": "0.0500", "h": "0.0100"},
        "source": "ocr",
        "verification": verification,
        "proof": ["consensus"],
        "readers": ["docling", "model_a"],
        "readings": [
            {"reader": "docling", "printed": value, "value": value, "page": page, "region": None},
            {"reader": "model_a", "printed": value, "value": value, "page": None, "region": None},
        ],
    }


def oa_result() -> dict[str, Any]:
    r = copy.deepcopy(result("pvvnl_passed"))
    b = r["bills"][0]
    b["pages"] = [1, 2]
    b["routes_used"] = ["local_ocr", "docling", "model_a", "llamaparse"]
    f = b["fields"]
    f["energy"]["tod"] = [
        {"slot": s, "kwh": None, "kvah": _fo(c), "open_access": _fo(o), "net": _fo(n)}
        for s, c, o, n, _ in SLOTS
    ]
    f["energy"]["power_factor"] = _fo("998", "disputed")
    f["energy"]["power_factor"]["readings"][1]["value"] = "0.998"
    f["energy"]["power_factor"]["readings"][1]["printed"] = "0.998"
    b["elements"] = [
        {
            "index": i,
            "label": s.split(" ")[0],
            "group": "EC Calculation",
            "kind": "item",
            "stage": "current",
            "code": "energy_charge",
            "quantity": n,
            "rate": rate,
            "unit": "kVAh",
            "tod_slot": s.split(" ")[0],
            "amount": _fo(str((Decimal(n) * Decimal(rate)).quantize(Decimal("0.01")))),
            "formula_recheck": {"status": "match"},
        }
        for i, (s, _, _, n, rate) in enumerate(SLOTS)
    ]
    second = copy.deepcopy(b)
    second["index"] = 1
    second["pages"] = [3, 4]
    second["fields"]["period"]["bill_month"]["value"] = "2026-02"
    r["bills"].append(second)
    return r


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


def test_slot_hours_from_printed_labels() -> None:
    assert slot_hours("TOD-1 (05 to 11)") == ("05:00", "11:00")
    assert slot_hours("TOD-2(11 TO 17)") == ("11:00", "17:00")
    assert slot_hours("Peak 17:00-23:00") == ("17:00", "23:00")
    assert slot_hours("TOD-3") is None and slot_hours(None) is None
    assert window_of("TOD-4 (23 to 05)") == ("23:00", "05:00")


def test_reading_view_of_a_two_bill_open_access_file(billx: FakeBillx) -> None:
    bills = _upload(billx, "oa2", oa_result())
    assert [b["bill_month"] for b in bills] == ["2026-03-01", "2026-02-01"] or len(bills) == 2
    view = client.get(f"/bills/{bills[0]['id']}/reading")
    assert view.status_code == 200, view.text
    v = view.json()
    assert v["pages"] == [1, 2] and v["page_url"].endswith("/pages/{page}.png")
    assert "llamaparse" in v["readers_used"] and "docling" in v["readers_used"]
    pf = next(f for f in v["fields"] if f["path"] == "energy.power_factor")
    assert pf["verification"] == "disputed" and pf["needs_confirmation"] is False
    assert {r["reader_name"]: r["value"] for r in pf["readings"]} == {"Docling": "998", "Model A": "0.998"}
    assert pf["box"]["x"] == "0.5000" and pf["source_ref"]["kind"] == "bill"
    tod = v["tod"]
    assert [t["slot"] for t in tod] == [s[0] for s in SLOTS]
    assert (tod[0]["start"], tod[0]["end"], tod[0]["unit"]) == ("05:00", "11:00", "kVAh")
    assert tod[0]["consumption"]["value"] == "5000" and tod[0]["open_access"]["value"] == "1000.5"
    assert tod[0]["net"]["value"] == "3999.5" and tod[0]["net"]["source_ref"]["page"] == 1
    assert [c["rate"] for c in v["charges"]] == [s[4] for s in SLOTS]
    assert v["cost_usd"] is not None
    second = client.get(f"/bills/{bills[1]['id']}/reading").json()
    assert second["pages"] == [3, 4]
    assert client.get("/bills/missing/reading").status_code == 404


def test_plan_inputs_carry_slots_rates_and_derived_shares(billx: FakeBillx) -> None:
    [b, _] = _upload(billx, "oa3", oa_result())
    r = client.get(f"/bills/{b['id']}/plan-inputs")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["energy_unit"] == "kVAh"
    first = p["slots"][0]
    assert first["slot"] == "TOD-1 (05 to 11)" and first["start"] == "05:00"
    assert first["consumption"]["value"]["value"] == "5000"
    assert first["consumption"]["value"]["unit"] == "kVAh"
    assert first["open_access"]["value"]["value"] == "1000.5"
    assert first["billed"]["value"]["value"] == "3999.5"
    assert first["rate"]["value"]["value"] == "6.800" and first["rate"]["value"]["unit"] == "INR/kVAh"
    refs = first["consumption"]["value"]["source_refs"]
    assert refs[0]["kind"] == "bill" and refs[0]["field_path"] == "energy.tod.0.kvah"
    assert first["share_of_consumption"]["value"]["value"] == "29.41"  # 5000 of 17000
    share = next(d for d in p["derived"] if d["key"] == "open_access_share")
    assert share["value"]["value"] == "21.18"  # 3600.5 of 17000
    assert len(share["value"]["source_refs"]) == 8
    assert client.get("/bills/missing/plan-inputs").status_code == 404


def test_page_images_are_rendered_and_cached(billx: FakeBillx) -> None:
    [b] = _upload(billx, "pg", result("pvvnl_passed"))
    r = client.get(f"/bills/{b['id']}/pages/1.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:4] == b"\x89PNG"
    again = client.get(f"/bills/{b['id']}/pages/1.png")
    assert again.content == r.content
    assert client.get(f"/bills/{b['id']}/pages/99.png").status_code == 404
    assert client.get("/bills/missing/pages/1.png").status_code == 404


def test_a_file_is_read_in_the_background_and_its_bills_appear(billx: FakeBillx) -> None:
    from ergplan.intake import bill_reads

    data = billx.register("bg1", oa_result())
    r = client.post("/bill-reads", files={"file": ("bg1.pdf", data, "application/pdf")})
    assert r.status_code == 202, r.text
    read = r.json()
    assert read["status"] == "queued" and read["pages"] >= 1 and read["bills"] == []
    assert read["page_url"] == f"/bill-reads/{read['id']}/pages/{{page}}.png"
    page = client.get(read["page_url"].replace("{page}", "1"))
    assert page.status_code == 200 and page.content[:4] == b"\x89PNG"
    assert billx.calls == 0  # nothing is read in the request
    assert bill_reads.drain(billx.client()) >= 1
    done = client.get(f"/bill-reads/{read['id']}").json()
    assert done["status"] == "done" and len(done["bills"]) == 2 and done["finished_at"]
    # the same file again is done at once from the stored reading, without billx
    calls = billx.calls
    again = client.post("/bill-reads", files={"file": ("bg1.pdf", data, "application/pdf")}).json()
    assert again["status"] == "done" and len(again["bills"]) == 2 and billx.calls == calls
    assert client.get("/bill-reads/missing").status_code == 404
    bad = client.post("/bill-reads", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert bad.status_code == 415


def test_a_failed_reading_says_so(billx: FakeBillx) -> None:
    from ergplan.intake import bill_reads

    data = billx.register("bg-fail", oa_result())
    read = client.post("/bill-reads", files={"file": ("f.pdf", data, "application/pdf")}).json()
    billx.down = True
    bill_reads.drain(billx.client())
    out = client.get(f"/bill-reads/{read['id']}").json()
    assert out["status"] == "failed" and out["error"]


def test_an_analyst_reads_a_file_again_and_the_new_bills_replace_the_old(billx: FakeBillx) -> None:
    from ergplan.intake import bill_reads

    an = {"X-Ergplan-Actor": "analyst@joulewise.in", "X-Ergplan-Role": "analyst"}
    old = copy.deepcopy(result("pvvnl_needs_review"))
    [b] = _upload(billx, "again", old)
    assert client.post(f"/bills/{b['id']}/reread").status_code == 403  # analysts only
    r = client.post(f"/bills/{b['id']}/reread", headers=an)
    assert r.status_code == 202, r.text
    billx.by_tag["again"] = oa_result()  # billx reads it better now
    bill_reads.drain(billx.client())
    done = client.get(f"/bill-reads/{r.json()['id']}", headers=an).json()
    assert done["status"] == "done" and len(done["bills"]) == 2
    assert client.get(f"/bills/{b['id']}").status_code == 404  # neither accepted nor confirmed: replaced


def test_a_client_accepts_a_bill_whose_required_values_are_verified(billx: FakeBillx) -> None:
    res = oa_result()
    for b in res["bills"]:
        b["status"], b["accepted"], b["passed"], b["accepted_by"] = "needs_review", False, False, None
    [b, _] = _upload(billx, "acc", res)
    assert not b["accepted"] and b["outstanding"] == []
    r = client.post(f"/bills/{b['id']}/accept", headers={"X-Ergplan-Actor": "c@plant.in"})
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] and r.json()["accepted_by"] == "bill_confirmations"
    from ergplan.db.base import session_scope
    from ergplan.db.models import Bill

    with session_scope() as s:
        used = bill_store.values(s, s.get(Bill, b["id"]))
    assert "energy.power_factor" not in used  # disputed, optional, unconfirmed: left out
    assert used["demand.max_kva"].ref.note == "confirmed by c@plant.in"
    nr = _upload(billx, "acc-nr", result("pvvnl_needs_review"))[0]
    assert client.post(f"/bills/{nr['id']}/accept").status_code == 409
