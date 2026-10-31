"""GET /connections/{id}/landed-cost and /rulebooks/limits."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ergplan.platform.app import app
from tests.platform.test_api_cost import connection  # noqa: F401  (fixture)

client = TestClient(app)


def test_landed_cost_default_scenario(connection: str) -> None:  # noqa: F811
    d = client.get(
        f"/connections/{connection}/landed-cost",
        params={"scenario": json.dumps({"as_of": "2026-06-01", "month": 6})},
    ).json()
    assert d["month"] == 6 and [s["name"] for s in d["slots"]] == ["normal", "solar", "peak"]
    src = {s["id"]: s for s in d["sources"]}
    grid = src["discom_grid"]["by_slot"]
    assert [g["slot"] for g in grid] == ["normal", "solar", "peak"]
    solar = src["oa_solar_intra"]["by_slot"][0]
    assert solar["lines"][0]["source_refs"][0]["kind"] == "assumption"  # the default PPA price
    css = next(x for x in solar["lines"] if "CSS" in (x["label"] or "") or "Industry" in (x["label"] or ""))
    assert css["value"] == "2.11" and css["source_refs"][0]["url"].endswith("#page=106")
    assert [b["slot"] for b in src["rooftop_pv"]["by_slot"]] == ["normal", "solar"]  # daylight slots only
    assert not src["iex_gdam"]["available"] and "GDAM" in src["iex_gdam"]["reason"]
    assert "regulatory_limits" in d["gaps"] and d["limits"] == []


def test_stated_price_and_ownership(connection: str) -> None:  # noqa: F811
    sc = {"sources": {"oa_solar_intra": {"price_inr_per_kwh": "2.95", "ownership": "captive"}}}
    d = client.get(f"/connections/{connection}/landed-cost", params={"scenario": json.dumps(sc)}).json()
    solar = next(s for s in d["sources"] if s["id"] == "oa_solar_intra")["by_slot"][0]
    assert (
        solar["lines"][0]["value"] == "2.95"
        and solar["lines"][0]["source_refs"][0]["kind"] == "client_stated"
    )


def test_landed_cost_errors(connection: str) -> None:  # noqa: F811
    assert client.get("/connections/missing/landed-cost").status_code == 404
    bad = client.get(f"/connections/{connection}/landed-cost", params={"scenario": "{nope"})
    assert bad.status_code == 422
    unknown = client.get(
        f"/connections/{connection}/landed-cost", params={"scenario": json.dumps({"sources": {"x": {}}})}
    )
    assert unknown.status_code == 422


def test_limits_endpoint(connection: str) -> None:  # noqa: F811
    assert client.get("/rulebooks/limits", params={"connection_id": connection}).json() == []
