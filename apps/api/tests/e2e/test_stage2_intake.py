"""Stage 2 end-to-end on real input: two real bills from different DISCOMs (NPCL in UP, MSEDCL in
Maharashtra; data/bills, gitignored) go through the running billx, come back `needs_review`, are
confirmed field by field through the API (the client's one-click "this is right"), become a
connection with twelve months of data and a synthesised load profile whose month matches the bill.
Needs billx at E2E_BILLX_URL (default http://localhost:8081) with E2E_BILLX_TOKEN."""

from __future__ import annotations

import os
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from ergplan.core.settings import REPO_ROOT
from ergplan.intake import bills as bill_store
from ergplan.intake.billx_client import BillxClient
from ergplan.platform.app import app

BILLS = REPO_ROOT / "data" / "bills"
URL = os.environ.get("E2E_BILLX_URL", "http://localhost:8081")
TOKEN = os.environ.get("E2E_BILLX_TOKEN", "dev-billx-token")
CASES = [
    ("NPCL Bill Plant May-June.pdf", "npcl", "UP", "HV-2"),
    ("bill_500_251019006990_202604.pdf", "msedcl", "MH", "HT I(A)"),
]


def _billx_up() -> bool:
    try:
        return (
            httpx.get(f"{URL}/v1/health", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=3).status_code
            == 200
        )
    except httpx.HTTPError:
        return False


pytestmark = [
    pytest.mark.external,
    pytest.mark.skipif(not all((BILLS / c[0]).exists() for c in CASES), reason="real bills not present"),
    pytest.mark.skipif(not _billx_up(), reason="billx not reachable"),
]


@pytest.mark.parametrize(("filename", "discom", "state", "category"), CASES)
def test_real_bill_to_connection_and_profile(
    monkeypatch: pytest.MonkeyPatch, filename: str, discom: str, state: str, category: str
) -> None:
    monkeypatch.setattr(bill_store, "BillxClient", lambda: BillxClient(base_url=URL, token=TOKEN))
    client = TestClient(app)
    data = (BILLS / filename).read_bytes()
    r = client.post("/bills", files={"file": (filename, data, "application/pdf")})
    assert r.status_code == 201, r.text
    bill = r.json()[0]
    assert bill["discom"] == discom
    # needs_review round trip: confirm every outstanding field with the value billx read
    for path in bill["outstanding"]:
        field = next(f for f in bill["fields"] if f["path"] == path)
        assert field["value"] is not None, f"{path} not read; the client would type it"
        r = client.post(
            f"/bills/{bill['id']}/confirm",
            json={"path": path, "value": field["value"]},
            headers={"X-Ergplan-Actor": "e2e-client@example.com"},
        )
        assert r.status_code == 200
        bill = r.json()
    assert bill["accepted"], bill["outstanding"]
    si = client.post("/intake/from-bills", json={"bill_ids": [bill["id"]]})
    assert si.status_code == 200, si.text
    intake = si.json()
    assert intake["state"]["value"] == state and intake["category"]["value"] == category
    built = client.post("/sites", json={"intake": intake})
    assert built.status_code == 201, built.text
    cid = built.json()["connection_id"]
    prof = client.get(f"/connections/{cid}/profile").json()
    assert len(prof["months"]) == 12 and prof["blocks"] in (365 * 96, 366 * 96)
    billed = next(m for m in prof["months"] if not m["extrapolated"])
    energy = next(f for f in bill["fields"] if f["path"] == "energy.kwh")["value"]
    assert Decimal(billed["energy_kwh"]["value"]) == Decimal(energy)
    assert billed["energy_kwh"]["source_refs"][0]["kind"] == "bill"
    md = Decimal(next(f for f in bill["fields"] if f["path"] == "demand.max_kva")["value"])
    pf = next((f["value"] for f in bill["fields"] if f["path"] == "energy.power_factor" and f["value"]), "1")
    assert abs(Decimal(billed["max_kw"]["value"]) - md * Decimal(pf)) < Decimal("0.01")
