"""GET /rulebooks/coverage: per state, which families are approved on a date and which are not yet sourced."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ergplan.platform.app import app

from ..engine.helpers import restore_committed

client = TestClient(app)


def test_coverage_shape_and_dates() -> None:
    restore_committed()
    r = client.get("/rulebooks/coverage")  # default: today
    assert r.status_code == 200
    rows = r.json()
    assert {"UP", "MH", "KA", "TS", "PB", "GJ"} <= {c["state"] for c in rows}
    for c in rows:
        assert set(c) == {"state", "name", "families", "jurisdictions"}
        assert set(c["families"].values()) <= {"approved", "not yet sourced"}
        for fam, status in c["families"].items():
            assert (status == "approved") == bool(c["jurisdictions"].get(fam)), (c["state"], fam)
    on = {c["state"]: c for c in client.get("/rulebooks/coverage", params={"on": "2026-11-01"}).json()}
    assert on["MH"]["families"]["tariff_schedule"] == "approved"
    assert "msedcl" in on["MH"]["jurisdictions"]["tariff_schedule"]
    early = client.get("/rulebooks/coverage", params={"on": "2000-01-01"}).json()
    assert all(set(c["families"].values()) == {"not yet sourced"} for c in early)
    assert client.get("/rulebooks/coverage", params={"on": "not-a-date"}).status_code == 422
