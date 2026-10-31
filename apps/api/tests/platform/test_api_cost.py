"""GET /connections/{id}/replay and /connections/{id}/avoided-cost on a synthetic MSEDCL bill shaped
like billx's output for the real April 2026 bill."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.intake import bills as bill_store
from ergplan.platform.app import app
from tests.engine.helpers import restore_committed
from tests.engine.test_replay_and_avoided import msedcl_bill
from tests.intake.helpers import FakeBillx

client = TestClient(app)


def _v(value: str, unit: str | None = None) -> dict[str, Any]:
    return {"value": value, "unit": unit, "verification": "verified", "page": 1, "proof": ["consensus"]}


def msedcl_result() -> dict[str, Any]:
    b = copy.deepcopy(msedcl_bill())
    f = b["fields"]
    f["period"]["bill_month"] = _v("2026-04")
    f["energy"]["kwh"] = _v("1446902", "kWh")
    f["energy"]["kvah"] = _v("1452509", "kVAh")
    f["energy"]["power_factor"] = _v("0.996")
    f["demand"]["max_kva"] = _v("2157", "kVA")
    f["demand"]["contract_kva"] = _v("2200", "kVA")
    f["tariff"] = {"category": _v("105 HT-I A")}
    f["consumer"] = {"name": _v("SYNTHETIC TEXTILES LTD")}
    b.update(
        {
            "status": "passed",
            "accepted": True,
            "accepted_by": "engine",
            "profile": {"id": "msedcl"},
            "review_reasons": [],
        }
    )
    return {"contract_version": "1.1", "bills": [b]}


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch) -> str:
    restore_committed()
    fake = FakeBillx()
    monkeypatch.setattr(bill_store, "BillxClient", fake.client)
    data = fake.register("msedcl", msedcl_result())
    [bill] = client.post("/bills", files={"file": ("m.pdf", data, "application/pdf")}).json()
    assert bill["accepted"]
    si = client.post("/intake/from-bills", json={"bill_ids": [bill["id"]]}).json()
    assert si["category"]["value"] == "HT I(A)" and si["voltage_kv"]["value"] == "22"
    out = client.post("/sites", json={"intake": si})
    assert out.status_code == 201, out.text
    return str(out.json()["connection_id"])


def test_replay_endpoint(connection: str) -> None:
    [r] = client.get(f"/connections/{connection}/replay").json()
    assert r["status"] == "explained" and r["evaluated_on"] == "2026-04-30"
    lines = {ln["group"]: ln for ln in r["lines"]}
    assert lines["demand"]["status"] == "match" and lines["energy"]["status"] == "match"
    assert lines["demand"]["computed"]["value"] == "1402050.00"
    assert lines["demand"]["billed"]["source_refs"][0]["field_path"] == "elements.4.amount"
    assert lines["demand"]["difference"]["value"] == "0.00"
    assert r["billed_total"]["source_refs"][0]["field_path"] == "totals.current_charges"
    refs = lines["energy"]["computed"]["source_refs"]
    assert any(x.get("url", "").startswith("/documents/") and "#page=" in x["url"] for x in refs)
    assert any(x["kind"] == "bill" for x in refs)
    assert "fppca_monthly" in r["gaps"] and r["file_url"].startswith("/bills/")
    assert any(t["code"] == "tod_adjustment" for t in r["tariff_lines"])


def test_avoided_cost_endpoint(connection: str) -> None:
    a = client.get(f"/connections/{connection}/avoided-cost", params={"as_of": "2026-06-01"}).json()
    assert len(a["matrix"]) == 12 and len(a["matrix"][0]) == 96
    assert a["tariff_as_of"] == "2026-06-01"
    rate = lambda m, b: float(a["cards"][a["matrix"][m][b]]["rate"]["value"])  # noqa: E731
    assert rate(0, 80) > rate(0, 40) > 0
    factor = next(c for c in a["cards"] if c["slot"] == "peak")["kvah_factor"]
    assert factor["source_refs"][0]["kind"] == "bill"  # kVAh / kWh from the bill
    assert a["annual"][0]["label"] == "Energy at avoided rates (year)"
    assert set(a["gaps"]) == {"fppca_monthly", "electricity_duty"}


def test_cost_endpoints_404_and_422() -> None:
    assert client.get("/connections/missing/replay").status_code == 404
    assert client.get("/connections/missing/avoided-cost").status_code == 404
