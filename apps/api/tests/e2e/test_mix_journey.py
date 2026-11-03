"""The client's own mix end to end (3 Nov 2026): a UP consumer (PVVNL, 33 kV) chooses captive solar,
wind and hybrid with purchases on the day-ahead and real-time exchange; the year is sized at least
cost over 15-minute blocks, settled by the judge (banking per ToD bucket with a carry-over ceiling),
and the result names each size and the exchange energy. The three-source mix failed re-settlement
before the bank's keep order was shared by the solver and the judge; the five-source mix failed
before the exchange followed the rule's set-off order. Marked `slow` (about four minutes)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.db.base import session_scope
from ergplan.intake import iex_loader
from ergplan.platform.app import app
from tests.intake.helpers import result
from tests.platform.test_api_mix import dam_csv
from tests.platform.test_api_plan import _truncate
from tests.platform.test_api_runs import CL, make_site

pytestmark = [pytest.mark.slow]
client = TestClient(app)
RE = ["oa_solar_intra", "oa_wind_intra", "oa_hybrid_intra"]


@pytest.mark.parametrize("kinds", [RE, [*RE, "iex_dam", "iex_rtm"]], ids=["re-only", "re-and-exchange"])
def test_a_up_mix_at_fifteen_minutes(monkeypatch: pytest.MonkeyPatch, kinds: list[str]) -> None:
    _truncate()
    try:
        _site, conn = make_site(monkeypatch, result("pvvnl_passed"), {"voltage_kv": "33"})
        with session_scope(actor="t") as s:
            iex_loader.store(s, iex_loader.parse(dam_csv(), "DAM_15min.csv"), "DAM_15min.csv", "t")
            rtm = dam_csv().replace(b"3600.00", b"3300.00")
            iex_loader.store(s, iex_loader.parse(rtm, "RTM_15min.csv", segment="rtm"), "RTM_15min.csv", "t")
        sources: list[dict[str, Any]] = [
            {"kind": k, "ownership": "captive"} if not k.startswith("iex_") else {"kind": k} for k in kinds
        ]
        r = client.post(
            f"/connections/{conn}/mix",
            params={"wait": "true"},
            json={"sources": sources, "resolution_min": 15},
            headers=CL,
        )
        out = r.json()
        assert r.status_code == 202 and out["status"] == "done", out
        sm = client.get(f"/runs/{out['run_id']}", headers=CL).json()["summary"]
        assert {z["kind"] for z in sm["sizes"]} == set(kinds)
        assert len(sm["monthly"]) == 12
        assert Decimal(sm["annual"]["saving"]["value"]) > 0
        for z in sm["sizes"]:
            if z["kind"].startswith("iex_"):
                assert z["exchange"]["segment"] == z["kind"].removeprefix("iex_")
    finally:
        _truncate()
