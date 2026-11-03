"""The client's own mix (journey step 5): the sources a consumer may choose, a mix of open-access
solar and wind with exchange purchases sized at least cost, the exchange bought block by block at
each block's clearing price (never sold), and the year's energy month by month."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.db.base import session_scope
from ergplan.db.models import Scenario
from ergplan.intake import iex_loader
from ergplan.optimizer.scenarios import ScenarioSpec
from ergplan.platform import runs as svc
from ergplan.platform.app import app
from ergplan.rulebook.repository import approved_rules
from tests.platform.test_api_plan import _truncate
from tests.platform.test_api_runs import CL, make_site, msedcl_5mw

client = TestClient(app)


def mcp(block: int) -> str:
    """INR/MWh by 15-minute block of the day (1–96): cheap at night, dear in the evening peak."""
    hour = (block - 1) // 4
    if hour < 6:
        return "2400.00"
    if hour < 17:
        return "3600.00"
    if hour < 23:
        return "9200.00"
    return "3000.00"


def dam_csv() -> bytes:
    """The first three days of every month of a year, every block (DAM layout)."""
    lines = [
        "Date,Time Block,Hour,Purchase Bid (MW),Sell Bid (MW),MCV (MW),Final Scheduled Volume (MW),MCP (₹/MWh)"
    ]
    for mo in range(1, 13):
        for d in range(1, 4):
            day = date(2025 if mo >= 4 else 2026, mo, d)
            for b in range(1, 97):
                start = timedelta(minutes=15 * (b - 1))
                end = start + timedelta(minutes=15)
                t0 = f"{start.seconds // 3600:02d}:{start.seconds % 3600 // 60:02d}"
                t1 = "24:00" if b == 96 else f"{end.seconds // 3600:02d}:{end.seconds % 3600 // 60:02d}"
                lines.append(f"{day.isoformat()},{t0} - {t1},{(b - 1) // 4 + 1},1,1,1,1,{mcp(b)}")
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture(scope="module")
def site() -> Iterator[dict[str, str]]:
    _truncate()
    mp = pytest.MonkeyPatch()
    try:
        site_id, conn = make_site(mp, msedcl_5mw(), {})
        with session_scope(actor="t") as s:
            iex_loader.store(s, iex_loader.parse(dam_csv(), "DAM_15min.csv"), "DAM_15min.csv", "t")
        yield {"site": site_id, "conn": conn}
    finally:
        mp.undo()
        _truncate()


@pytest.fixture(autouse=True)
def clean_db() -> None:  # the module's site is shared by its tests
    return None


def test_the_sources_a_client_may_choose(site: dict[str, str]) -> None:
    r = client.get(f"/connections/{site['conn']}/mix/options", headers=CL)
    assert r.status_code == 200, r.text
    by = {o["kind"]: o for o in r.json()}
    assert by["iex_dam"]["available"] and by["iex_dam"]["ownerships"] == []
    assert not by["iex_gdam"]["available"] and "GDAM" in by["iex_gdam"]["reason"]
    assert by["oa_wind_intra"]["group"] == "Wind" and by["oa_solar_ists"]["connection"] == "ists"
    assert by["oa_hybrid_intra"]["default_price_inr_per_kwh"] == "3.50"
    assert by["btm_bess"]["group"] == "At your site"
    assert client.get("/connections/missing/mix/options", headers=CL).status_code == 404


def test_exchange_energy_is_priced_block_by_block(site: dict[str, str]) -> None:
    with session_scope(actor="t") as s:
        sc = Scenario(
            site_id=site["site"],
            connection_id=site["conn"],
            name="probe",
            spec={},
            created_by="t",
        )
        spec = ScenarioSpec.model_validate(
            {"candidates": [{"kind": "iex_dam"}], "as_of": "2026-06-01", "resolution_min": 15}
        )
        a = svc.assemble(s, sc, spec, approved_rules)
    cand = a.problem.candidates[0]
    blocks = a.problem.blocks
    june = [t for t, b in enumerate(blocks) if b.month.month == 6]
    by_q: dict[int, set[float]] = {}
    for t in june[:96]:
        by_q.setdefault(t % 96, set()).add(round(cand.energy_inr_per_kwh[t], 6))
    night, day, evening = by_q[8].pop(), by_q[48].pop(), by_q[80].pop()  # 02:00, 12:00, 20:00
    assert night < day < evening
    # the landed cost rises with the clearing price by the same slope in every block of a slot
    assert evening - day == pytest.approx((9.2 - 3.6) * (evening - day) / (9.2 - 3.6))
    assert cand.dispatchable and cand.category == "exchange"


def test_a_mix_of_solar_wind_and_the_exchange_is_sized_at_least_cost(site: dict[str, str]) -> None:
    body = {
        "sources": [
            {"kind": "oa_solar_intra", "ownership": "captive", "max_mw": "6"},
            {"kind": "oa_wind_intra", "ownership": "captive", "price_inr_per_kwh": "3.40", "max_mw": "6"},
            {"kind": "iex_dam", "max_mw": "4"},
        ],
        "resolution_min": 60,
        "as_of": "2026-06-01",
    }
    r = client.post(f"/connections/{site['conn']}/mix", params={"wait": "true"}, json=body, headers=CL)
    assert r.status_code == 202, r.text
    out = r.json()
    assert out["name"] == "Your mix" and out["status"] == "done", out
    run = client.get(f"/runs/{out['run_id']}", headers=CL).json()
    sm = run["summary"]
    sizes = {z["kind"]: z for z in sm["sizes"]}
    assert set(sizes) == {"oa_solar_intra", "oa_wind_intra", "iex_dam"}
    ex = sizes["iex_dam"]["exchange"]
    assert ex["segment"] == "dam" and ex["blocks_bought"] >= 0
    bought = Decimal(sizes["iex_dam"]["delivered_kwh"]["value"])
    peak = Decimal(sizes["iex_dam"]["kw"]["value"])
    assert peak <= Decimal("4000.001")
    if bought > 0:
        assert Decimal(ex["avg_landed"]["value"]) > 0 and ex["avg_landed"]["source_refs"]
        assert any(r["kind"] == "market" for r in ex["avg_landed"]["source_refs"])
    for z in sm["sizes"]:
        assert Decimal(z["kw"]["value"]) >= 0 and z["kw"]["source_refs"]
    # where the year's consumption came from, month by month: set-off, bank, grid (no battery here)
    assert len(sm["monthly"]) == 12
    for row in sm["monthly"]:
        total = Decimal(row["grid_kwh"]["value"]) + Decimal(row["withdrawn_kwh"]["value"])
        total += sum((Decimal(v["value"]) for v in row["sources"].values()), Decimal(0))
        assert abs(total - Decimal(row["load_kwh"]["value"])) <= Decimal("0.05"), row["month"]
    assert Decimal(sm["annual"]["saving"]["value"]) > 0
    # DAM power is grid-mix power: it keeps the grid's emission factor
    factor = Decimal(sm["emissions"]["factor"]["value"])
    grid = Decimal(sm["settlement"]["grid_kwh"]["value"])
    after = Decimal(sm["emissions"]["after_t"]["value"])
    assert abs(after - (grid + bought) * factor / 1000) <= Decimal("0.01")
    # asking again with other sources replaces the scenario's spec, not the run
    again = dict(body, sources=body["sources"][:1])
    r2 = client.post(f"/connections/{site['conn']}/mix", json=again, headers=CL).json()
    assert r2["scenario_id"] == out["scenario_id"] and r2["run_id"] != out["run_id"]
    with session_scope(actor="t") as s:
        sc = s.get(Scenario, out["scenario_id"])
        assert sc is not None and len(sc.spec["candidates"]) == 1


@pytest.mark.parametrize(
    ("sources", "words"),
    [
        ([{"kind": "btm_bess"}], "needs a source"),
        ([{"kind": "rooftop_pv"}, {"kind": "rooftop_pv"}], "at most one"),
        ([{"kind": "oa_solar_intra"}, {"kind": "oa_solar_intra"}], "each source once"),
        ([{"kind": "iex_gdam"}], "GDAM"),
        ([{"kind": "discom_grid"}], ""),
    ],
)
def test_a_mix_the_api_refuses(site: dict[str, str], sources: list[dict[str, Any]], words: str) -> None:
    r = client.post(f"/connections/{site['conn']}/mix", json={"sources": sources}, headers=CL)
    assert r.status_code == 422 and words in r.text
