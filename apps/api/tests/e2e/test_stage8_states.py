"""Stage 8 breadth: the newly approved states (Karnataka ESCOMs, Telangana DISCOMs, Punjab PSPCL) price a
typed site through the same engines, with every rate citing its order page; states without approved
rules show "not yet sourced"."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.platform.app import app

from ..engine.helpers import restore_committed

client = TestClient(app)
F = lambda v: {"value": v}  # noqa: E731


def intake(discom: str, state: str, category: str, kv: str, cd: str) -> dict[str, Any]:
    return {
        "client_name": F(f"Test {discom}"),
        "site_name": F("Works"),
        "state": F(state),
        "discom": F(discom),
        "category": F(category),
        "voltage_kv": F(kv),
        "contract_demand_kva": F(cd),
        "industry_shape": F("steel_induction"),
        "weekly_off": F([6]),
        "months": [
            {
                "month": "2026-04-01",
                "energy": F("600000"),
                "max_kva": F(str(int(Decimal(cd) * Decimal("0.8")))),
            }
        ],
    }


CASES = [
    # discom, state, category, kV, CD, month index (Apr=0 for a year from April), block, expected INR/kWh before kVAh factor
    ("bescom", "KA", "HT-2(a)", "11", "1500", 0, 28, Decimal("7.60")),  # April 07:00: 660 paise + (+)100
    ("bescom", "KA", "HT-2(a)", "11", "1500", 4, 28, Decimal("6.60")),  # August (monsoon): no ToD
    ("tgspdcl", "TS", "HT-I(A)", "33", "3000", 0, 30, Decimal("8.65")),  # 07:30: 7.15 + 1.50 per kVAh
    ("tgspdcl", "TS", "HT-I(A)", "33", "3000", 0, 50, Decimal("6.65")),  # 12:30: 7.15 - 0.50
    (
        "pspcl",
        "PB",
        "LS General Industry",
        "11",
        "2000",
        0,
        50,
        Decimal("6.00"),
    ),  # above 1000 kVA, no ToD rows
]


@pytest.mark.parametrize(("discom", "state", "cat", "kv", "cd", "month", "block", "expected"), CASES)
def test_new_state_avoided_cost_cites_its_order(
    discom: str, state: str, cat: str, kv: str, cd: str, month: int, block: int, expected: Decimal
) -> None:
    restore_committed()
    out = client.post("/sites", json={"intake": intake(discom, state, cat, kv, cd)})
    assert out.status_code == 201, out.text
    cid = out.json()["connection_id"]
    a = client.get(f"/connections/{cid}/avoided-cost", params={"as_of": "2026-11-01"}).json()
    card = a["cards"][a["matrix"][month][block]]
    factor = Decimal(card["kvah_factor"]["value"]) if card["kvah_factor"] else Decimal(1)
    assert Decimal(card["rate"]["value"]) == pytest.approx(expected * factor, abs=Decimal("0.0001"))
    pages = {r["page"] for c in card["components"] for r in c["source_refs"] if r.get("page")}
    assert pages, card


def test_coverage_names_what_is_not_yet_sourced() -> None:
    restore_committed()
    cov = {c["state"]: c for c in client.get("/rulebooks/coverage", params={"on": "2026-11-01"}).json()}
    for st in ("KA", "TS", "PB"):
        assert cov[st]["families"]["tariff_schedule"] == "approved", st
        assert cov[st]["families"]["oa_charge"] == "approved", st
    assert set(cov["KA"]["jurisdictions"]["oa_charge"]) == {
        "ka_escoms",
        "bescom",
        "mescom",
        "cesc",
        "hescom",
        "gescom",
    }
    assert cov["TS"]["families"]["oa_charge"] == "approved"  # CSS and T&D charges per DISCOM
    assert set(cov["TS"]["jurisdictions"]["oa_charge"]) == {"tgspdcl", "tgnpdcl"}
    assert cov["TS"]["families"]["settlement"] == "not yet sourced"  # banking: TGERC OA regulations
    assert (
        cov["KA"]["families"]["tod_slots"] == "approved"
        and cov["PB"]["families"]["tod_slots"] == "not yet sourced"
    )
    for st in ("GJ", "RJ", "HR"):
        assert set(cov[st]["families"].values()) == {"not yet sourced"}, st
    assert cov["UP"]["families"]["settlement"] == "approved"


@pytest.mark.parametrize(
    ("discom", "kv", "css", "wheeling", "css_page"),
    [("tgspdcl", "33", "1.73", "0.09", 152), ("tgnpdcl", "132", "1.69", "0.12", 154)],
)
def test_telangana_open_access_cites_css_and_td_charges(
    discom: str, kv: str, css: str, wheeling: str, css_page: int
) -> None:
    restore_committed()
    out = client.post("/sites", json={"intake": intake(discom, "TS", "HT-I(A)", kv, "3000")})
    cid = out.json()["connection_id"]
    sc = {"as_of": "2026-11-01", "month": 11, "sources": {"oa_solar_intra": {"ownership": "third_party"}}}
    d = client.get(f"/connections/{cid}/landed-cost", params={"scenario": json.dumps(sc)}).json()
    solar = next(s for s in d["sources"] if s["id"] == "oa_solar_intra")["by_slot"][0]
    by_value = {(ln["label"] or ""): ln for ln in solar["lines"]}
    css_line = next(ln for lbl, ln in by_value.items() if "CSS" in lbl)
    assert css_line["value"] == css and css_line["source_refs"][0]["url"].endswith(f"#page={css_page}")
    td = next(ln for lbl, ln in by_value.items() if "T&D" in lbl or "wheeling" in lbl.lower())
    assert td["value"] == wheeling and td["source_refs"][0]["page"] == 152


def _oa_solar(discom: str, state: str, cat: str, kv: str) -> dict[str, Any]:
    restore_committed()
    cid = client.post("/sites", json={"intake": intake(discom, state, cat, kv, "3000")}).json()[
        "connection_id"
    ]
    sc = {"as_of": "2026-11-01", "month": 11, "sources": {"oa_solar_intra": {"ownership": "third_party"}}}
    d = client.get(f"/connections/{cid}/landed-cost", params={"scenario": json.dumps(sc)}).json()
    out: dict[str, Any] = next(s for s in d["sources"] if s["id"] == "oa_solar_intra")["by_slot"][0]
    return out


def test_karnataka_open_access_css_wheeling_and_loss() -> None:
    solar = _oa_solar("mescom", "KA", "HT-2(a)", "11")
    lines = {(ln["label"] or ""): ln for ln in solar["lines"]}
    css = next(ln for lbl, ln in lines.items() if lbl.startswith("CSS"))
    assert css["value"] == "1.86" and css["source_refs"][0]["page"] == 260
    wh = next(ln for lbl, ln in lines.items() if lbl.startswith("HT network wheeling"))
    assert wh["value"] == "0.44" and wh["source_refs"][0]["page"] == 249
    assert any(lbl.startswith("Losses") and "HT technical loss" in lbl for lbl in lines)
    assert any(lbl.startswith("Additional surcharge") and ln["value"] == "0" for lbl, ln in lines.items())


def test_punjab_renewable_wheeling_in_kind_and_css() -> None:
    solar = _oa_solar("pspcl", "PB", "LS General Industry", "11")
    lines = {(ln["label"] or ""): ln for ln in solar["lines"]}
    assert next(ln for lbl, ln in lines.items() if lbl.startswith("CSS"))["value"] == "0.86"
    loss = next(lbl for lbl in lines if lbl.startswith("Losses"))
    assert "2 %" in loss and "2.19" in loss and "4.00" in loss  # in-kind wheeling, transmission, 11 kV
