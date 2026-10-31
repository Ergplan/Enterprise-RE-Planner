"""Stage 6 end to end: the real NPCL July–August bill (billx's stored reading) dropped and built into a
site, then step 5 — three scenarios sized at 15 minutes, each re-settled by the judge, compared side by
side; one replayed from its pins to the paisa. Marked `slow` (several minutes)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from ergplan.intake import bills as bill_store
from ergplan.intake.billx_client import BillxClient
from ergplan.platform.app import app

from ..engine.helpers import restore_committed
from .test_stage4_landed import BILL, _cached

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(_cached() is None, reason="the real NPCL bill or its billx reading is not present"),
]
AN = {"X-Ergplan-Actor": "analyst@joulewise.in", "X-Ergplan-Role": "analyst"}
CL = {"X-Ergplan-Actor": "client@acme.in", "X-Ergplan-Role": "client"}


def test_bill_drop_to_step_five(monkeypatch: pytest.MonkeyPatch) -> None:
    restore_committed()
    res = _cached()
    assert BILL is not None and res is not None
    t = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"job_id": "j", "status": "done", "result": res})
    )
    monkeypatch.setattr(
        bill_store, "BillxClient", lambda: BillxClient(base_url="http://b", token="t", transport=t)
    )
    client = TestClient(app)
    [bill] = client.post("/bills", files={"file": ("npcl.pdf", BILL.read_bytes(), "application/pdf")}).json()
    for path in bill["outstanding"]:
        value = next(f["value"] for f in bill["fields"] if f["path"] == path)
        bill = client.post(f"/bills/{bill['id']}/confirm", json={"path": path, "value": value}).json()
    si = client.post(
        "/intake/from-bills", json={"bill_ids": [bill["id"]], "overrides": {"voltage_kv": "33"}}
    ).json()
    out = client.post("/sites", json={"intake": si}).json()
    site, conn = out["site_id"], out["connection_id"]
    base = {"as_of": "2026-09-01", "resolution_min": 15}
    specs = {
        "Captive solar": [{"kind": "oa_solar_intra", "ownership": "captive"}],
        "Hybrid + battery": [{"kind": "oa_hybrid_intra", "ownership": "third_party"}, {"kind": "btm_bess"}],
        "Rooftop + solar + battery": [
            {"kind": "rooftop_pv"},
            {"kind": "oa_solar_intra", "ownership": "captive"},
            {"kind": "btm_bess"},
        ],
    }
    runs = {}
    for name, cands in specs.items():
        sid = client.post(
            f"/sites/{site}/scenarios",
            json={"connection_id": conn, "name": name, "spec": {**base, "candidates": cands}},
            headers=AN,
        ).json()["id"]
        r = client.post(f"/scenarios/{sid}/run", params={"wait": "true"}, headers=AN).json()
        assert r["status"] == "done", (name, r["error"])
        assert r["solver"]["seconds"] < 120 and Decimal(r["analyst"]["resettle"]["max_diff_kwh"]) <= 1
        runs[name] = r
    board = client.get(f"/sites/{site}/scenarios", headers=CL).json()
    assert [b["name"] for b in board] == list(specs) and all(b["latest_run"]["summary"] for b in board)
    for b in board:
        s = b["latest_run"]["summary"]
        assert Decimal(s["annual"]["saving"]["value"]) > 0
        assert any(ref.get("page") for ref in s["annual"]["after"]["source_refs"])
    rp = client.post(
        f"/runs/{runs['Captive solar']['id']}/replay", params={"wait": "true"}, headers=AN
    ).json()
    assert rp["identical_to_original"] is True
    d = client.get(f"/runs/{runs['Hybrid + battery']['id']}/dispatch", headers=CL).json()
    assert d["minutes"] == 15 and len(d["times"]) == 7 * 96
