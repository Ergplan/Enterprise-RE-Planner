"""Stage 4 end to end: the real NPCL July–August bill (billx's stored reading) dropped, confirmed and
built into a site; step 3's landed costs follow, every non-price line citing a stored order page."""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ergplan.core.settings import REPO_ROOT
from ergplan.intake import bills as bill_store
from ergplan.intake.billx_client import BillxClient
from ergplan.platform.app import app

from ..engine.helpers import restore_committed

BILL = next((REPO_ROOT / "data" / "bills").rglob("NPCL July - Aug Plant.pdf"), None)
RESULTS = REPO_ROOT / "data" / "bills" / "billx-results"


def _cached() -> dict[str, object] | None:
    if BILL is None:
        return None
    p = RESULTS / f"{hashlib.sha256(BILL.read_bytes()).hexdigest()}.json"
    return json.loads(p.read_text())["result"] if p.exists() else None


pytestmark = pytest.mark.skipif(
    _cached() is None, reason="the real NPCL bill or its billx reading is not present"
)


def test_bill_drop_to_step_three(monkeypatch: pytest.MonkeyPatch) -> None:
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
    cid = client.post("/sites", json={"intake": si}).json()["connection_id"]
    d = client.get(
        f"/connections/{cid}/landed-cost",
        params={"scenario": json.dumps({"as_of": "2026-09-01", "month": 7})},
    ).json()
    src = {s["id"]: s for s in d["sources"]}
    assert len(d["avoided"]) == len(d["slots"]) == 4
    solar = src["oa_solar_intra"]["by_slot"][0]
    for line in solar["lines"][1:]:
        assert any(
            (r.get("url") or "").startswith("/documents/") and "#page=" in r["url"]
            for r in line["source_refs"]
        ), line
    # 3.10 + STU 0.3075 + wheeling 1.03 + STU-loss gross-up + CSS 0.51 (11–66 kV) + AS 0
    assert abs(float(solar["total"]["value"]) - 5.0933) < 0.0001
    rtm = next((REPO_ROOT / "data" / "iex").glob("RTM_*.xlsx"), None)
    if rtm is not None:  # load the real RTM file through the analyst endpoint, then IEX RTM lands too
        up = client.post(
            "/prices",
            files={"file": (rtm.name, rtm.read_bytes())},
            headers={"X-Ergplan-Actor": "analyst@joulewise.in", "X-Ergplan-Role": "analyst"},
        )
        assert up.status_code == 201
        d = client.get(
            f"/connections/{cid}/landed-cost",
            params={"scenario": json.dumps({"as_of": "2026-09-01", "month": 7})},
        ).json()
        iex = next(s for s in d["sources"] if s["id"] == "iex_rtm")
        assert iex["available"] and iex["by_slot"][0]["lines"][0]["source_refs"][0]["kind"] == "market"
