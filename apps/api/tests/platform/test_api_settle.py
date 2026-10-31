"""POST /connections/{id}/settle on the synthetic MSEDCL connection, and the generation curves."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from ergplan.intake import generation
from ergplan.platform.app import app
from tests.platform.test_api_cost import connection  # noqa: F401  (fixture)

client = TestClient(app)
AN = {"X-Ergplan-Actor": "analyst@joulewise.in", "X-Ergplan-Role": "analyst"}


def test_settle_normative_solar(connection: str) -> None:  # noqa: F811
    body = {
        "sources": [{"id": "pv", "kind": "oa_solar_intra", "capacity_mw": "1.5", "ownership": "captive"}],
        "as_of": "2026-06-01",
    }
    assert client.post(f"/connections/{connection}/settle", json=body).status_code == 403
    r = client.post(f"/connections/{connection}/settle", json=body, headers=AN)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["granularity"] == "tod_slot_monthly" and "Regulation 20.3" in (d["rule"] or "")
    assert len(d["months"]) == 12 and d["sources"][0]["delivered_share"] == "1"  # no MSEDCL OA loss rows yet
    lines = {x["label"]: Decimal(x["value"]) for x in d["statement"]}
    assert (
        lines["Consumption"]
        == lines["Set off from pv"] + lines["Withdrawn from the bank"] + lines["Drawn from the DISCOM"]
    )
    assert lines["Banked (after the charge in kind)"] == lines["Withdrawn from the bank"] + lines["Lapsed"]
    assert any("normative solar curve" in n for n in d["notes"])
    page_refs = [r for x in d["statement"] for r in x["source_refs"] if r.get("page")]
    assert page_refs and all(r["url"].startswith("/documents/") for r in page_refs)


def test_settle_errors(connection: str) -> None:  # noqa: F811
    bad = {"sources": [{"id": "g", "kind": "discom_grid", "capacity_mw": "1"}]}
    assert client.post(f"/connections/{connection}/settle", json=bad, headers=AN).status_code == 422
    short = {"sources": [{"id": "pv", "kind": "oa_solar_intra", "capacity_mw": "1", "kw": ["1", "2"]}]}
    assert client.post(f"/connections/{connection}/settle", json=short, headers=AN).status_code == 422
    assert client.post("/connections/missing/settle", json=short, headers=AN).status_code == 404


def test_generation_profile_scales_to_cuf() -> None:
    kw, cuf = generation.profile(generation.curve_for("solar", "UP"), Decimal(1000), date(2026, 4, 1))
    assert len(kw) == 365 * 96 and cuf == Decimal(20)
    energy = sum(kw, Decimal(0)) / 4
    assert abs(energy - Decimal(1000) * 8760 * Decimal("0.20")) < 1
    assert kw[0] == 0 and max(kw) <= 1000  # dark at midnight, never above capacity
    hyb, cuf2 = generation.profile(generation.curve_for("hybrid", "MH"), Decimal(1000), date(2026, 4, 1))
    assert cuf2 == Decimal("24.5") and hyb[0] > 0
    with pytest.raises(generation.CurveNotFound):
        generation.curve("solar_xx")
