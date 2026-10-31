"""Stage 8 breadth: the newly approved states (Karnataka ESCOMs, Telangana DISCOMs, Punjab PSPCL) price a
typed site through the same engines, with every rate citing its order page; states without approved
rules show "not yet sourced"."""

from __future__ import annotations

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
        assert cov[st]["families"]["oa_charge"] == "not yet sourced", st
    assert (
        cov["KA"]["families"]["tod_slots"] == "approved"
        and cov["PB"]["families"]["tod_slots"] == "not yet sourced"
    )
    for st in ("GJ", "RJ", "HR"):
        assert set(cov[st]["families"].values()) == {"not yet sourced"}, st
    assert cov["UP"]["families"]["settlement"] == "approved"
