"""The two 5 MVA test sites (synthetic MSEDCL HT-I(A) bill scaled to 5 MVA; PVVNL HV-2 at 5 MVA)
solved at 15 minutes: within two minutes, with the judge agreeing (invariant 6). Marked `slow`: run
by CI's site step and the Stage 6 end-to-end, not by the watcher on every save."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from ergplan.platform.app import app
from tests.intake.helpers import result
from tests.platform.test_api_runs import AN, make_site, msedcl_5mw

client = TestClient(app)
pytestmark = pytest.mark.slow

CASES = {
    "mh": (
        msedcl_5mw,
        {},
        "2026-06-01",
        [
            {"kind": "oa_hybrid_intra", "ownership": "third_party", "max_mw": "10"},
            {"kind": "rooftop_pv", "max_mw": "1.5"},
            {"kind": "btm_bess", "max_mw": "2"},
        ],
    ),
    "up": (
        lambda: result("pvvnl_passed"),
        {"voltage_kv": "33"},
        "2026-09-01",
        [
            {"kind": "oa_solar_intra", "ownership": "captive", "max_mw": "12"},
            {"kind": "btm_bess", "max_mw": "2"},
        ],
    ),
}


@pytest.mark.parametrize("state", sorted(CASES))
def test_five_mw_site_at_15_minutes(state: str, monkeypatch: pytest.MonkeyPatch) -> None:
    res, overrides, as_of, cands = CASES[state]
    site, conn = make_site(monkeypatch, res(), overrides)
    spec = {"candidates": cands, "as_of": as_of, "resolution_min": 15}
    sid = client.post(
        f"/sites/{site}/scenarios", json={"connection_id": conn, "name": "site", "spec": spec}, headers=AN
    ).json()["id"]
    run = client.post(f"/scenarios/{sid}/run", params={"wait": "true"}, headers=AN).json()
    assert run["status"] == "done", run["error"]
    assert run["solver"]["blocks"] == 35040 and run["solver"]["seconds"] < 120
    assert Decimal(run["analyst"]["resettle"]["max_diff_kwh"]) <= Decimal("1")
    assert Decimal(run["summary"]["annual"]["saving"]["value"]) > 0
