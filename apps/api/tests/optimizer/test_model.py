"""Every constraint family on tiny models (a few blocks) with optima worked by hand, and the judge's
agreement on each (invariant 6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from ergplan.optimizer.highs_solve import Solution, solve
from ergplan.optimizer.model import Battery, BlockMeta, Candidate, Grid, Limit, Problem, Thermal
from ergplan.optimizer.resettle import resettle, status_quo
from ergplan.rulebook.models import RuleView

APR, MAY = date(2026, 4, 1), date(2026, 5, 1)


def P(
    load: list[float],
    cands: list[Candidate] = (),  # type: ignore[assignment]
    rule: dict[str, Any] | None = None,
    rate: float | list[float] = 8.0,
    months: list[date] | None = None,
    slots: list[str] | None = None,
    grid: dict[str, Any] | None = None,
    **kw: Any,
) -> Problem:
    n = len(load)
    months = months or [APR] * n
    slots = slots or ["day"] * n
    blocks = [BlockMeta(months[i], slots[i], frozenset({slots[i]}), i) for i in range(n)]
    rates = rate if isinstance(rate, list) else [rate] * n
    g = Grid(rate=rates, demand_rate={}, **(grid or {}))
    r = (
        RuleView(
            id="r",
            family="settlement",
            version_id="v",
            jurisdiction_id="X",
            scope={},
            body=rule,
            source_ref={},
        )
        if rule
        else None
    )
    return Problem(blocks=blocks, hours=1.0, load_kwh=load, grid=g, candidates=list(cands), rule=r, **kw)


def check(p: Problem) -> Solution:
    s = solve(p)
    rs = resettle(p, s, Decimal("0.01"))
    assert rs.agrees, (rs.max_diff_kwh, rs.by_month)
    return s


def pv(shape: list[float], **kw: Any) -> Candidate:
    return Candidate(
        "pv", shape=shape, energy_inr_per_kwh=[3.0] * len(shape), max_kw=kw.pop("max_kw", 100), **kw
    )


def test_grid_only_cost_is_the_status_quo() -> None:
    p = P([10, 20, 30], grid={"cd_kva": 40, "floor_pct": 75}, rate=[5, 6, 7])
    s = check(p)
    assert s.objective == pytest.approx(5 * 10 + 6 * 20 + 7 * 30)
    assert status_quo(p)["grid_energy"] == Decimal("380.00")


def test_must_take_oa_sized_where_the_last_kw_stops_paying() -> None:
    # +1 kW brings 1.5 kWh at 3 INR = 4.5; it saves 8 × 1.5 until block 1 is full at 10 kW, then 8 × 0.5 = 4
    s = check(P([10, 10, 10], [pv([1, 0.5, 0])]))
    assert s.cap_kw["pv"] == pytest.approx(10)


BANK_POOLED = {
    "granularity": "block_15min",
    "banking": {
        "allowed": True,
        "buckets": "pooled",
        "period": "monthly",
        "charge": {"kind": "in_kind_percent", "value": "10"},
    },
}


def test_banking_charge_in_kind() -> None:
    # all generation is banked at 90%; 20 kWh of later load → 20 / 0.9 kW
    s = check(P([0, 10, 10], [pv([1, 0, 0], may_bank=True)], BANK_POOLED))
    assert s.cap_kw["pv"] == pytest.approx(20 / 0.9)
    assert s.settled[APR]["charge"] == pytest.approx(20 / 9, abs=1e-3)  # dispatch read to the watt-hour


def test_drawal_window_masks() -> None:
    rule = {
        "granularity": "block_15min",
        "banking": {
            "allowed": True,
            "buckets": "per_slot",
            "period": "monthly",
            "charge": {"kind": "in_kind_percent", "value": "10"},
            "drawal_windows": [{"deposited_in_slots": ["solar"], "allowed_slots": ["solar"]}],
        },
    }
    p = P([0, 10, 5], [pv([1, 0, 0], may_bank=True)], rule, slots=["solar", "peak", "solar"])
    s = check(p)
    assert s.cap_kw["pv"] == pytest.approx(5 / 0.9)  # only the later solar block may draw


def test_carry_over_ceiling_and_lapse() -> None:
    rule = {
        "granularity": "block_15min",
        "banking": {
            "allowed": True,
            "buckets": "pooled",
            "period": "monthly",
            "carry_over": True,
            "cap": {"pct_of_injection": "50"},
            "charge": {"kind": "in_kind_percent", "value": "10"},
        },
    }
    # April banks 0.9c, may keep 0.5c (50% of injection) for May's 100 kWh; the rest lapses
    p = P([0, 100], [pv([1, 0], may_bank=True, max_kw=1000)], rule, months=[APR, MAY])
    s = check(p)
    assert s.cap_kw["pv"] == pytest.approx(200)
    assert s.settled[APR]["lapsed"] == pytest.approx(80)


def test_carry_over_higher_of_two_ceilings() -> None:
    rule = {
        "granularity": "block_15min",
        "banking": {
            "allowed": True,
            "buckets": "pooled",
            "period": "monthly",
            "carry_over": True,
            "cap": {"pct_of_injection": "10", "pct_of_consumption": "50", "combine": "higher"},
        },
    }
    # 50 kW fixed. April: 100 kWh from the grid, so the consumption ceiling (50) beats 10% of the 50 kWh
    # injected (5): all 50 banked kWh carry into May. Sizing takes the lower ceiling (conservative);
    # the settlement pass applies the rule's higher one.
    pv50 = pv([0, 1, 0], may_bank=True, min_kw=50, max_kw=50)
    s = check(P([100, 0, 50], [pv50], rule, months=[APR, APR, MAY]))
    assert s.settled[APR]["lapsed"] == pytest.approx(0)
    assert s.settled[MAY]["withdrawn"] == pytest.approx(50)


def test_tod_slot_netting_offsets_within_the_slot() -> None:
    rule = {"granularity": "tod_slot_monthly", "banking": {"allowed": False}}
    s = check(P([0, 10], [pv([1, 0])], rule, slots=["solar", "solar"]))
    assert s.cap_kw["pv"] == pytest.approx(10)
    s2 = check(P([0, 10], [pv([1, 0])], {"granularity": "block_15min", "banking": {"allowed": False}}))
    assert s2.cap_kw["pv"] == pytest.approx(0)


def test_battery_arbitrage() -> None:
    b = Battery(
        "bess",
        max_kw=100,
        min_hours=0,
        max_hours=4,
        eff_charge=0.9,
        eff_discharge=1.0,
        inr_per_kw_year=0.5,
        inr_per_kwh_year=0.5,
    )
    s = check(P([10, 10, 10], rate=[2, 10, 10], batteries=[b]))
    # charge 22.2 kWh at 2, deliver 20 kWh at 10 over the two dear blocks
    assert s.bess_kwh["bess"] == pytest.approx(20)
    assert s.bess_kw["bess"] == pytest.approx(200 / 9)


def test_demand_floor_and_contract_demand_step() -> None:
    grid = {
        "cd_kva": 60,
        "floor_pct": 75,
        "pf": 1.0,
        "cd_step_kva": 10,
        "cd_min_kva": 10,
        "cd_max_kva": 60,
        "cd_change_inr_per_kva_year": 1.0,
        "excess_rate": {APR: 200.0},
    }
    p = P([10, 30, 10], rate=0.0, grid=grid)
    p.grid.demand_rate[APR] = 100.0
    s = check(p)
    # demand 30 kVA: 30 and 40 kVA give the same billing demand (floor 22.5 / 30); 40 is the smaller change
    assert s.cd_kva == pytest.approx(40)
    assert s.objective == pytest.approx(30 * 100 + 20 * 1)


def test_thermal_min_down_tech_min_and_ramp() -> None:
    u = Thermal(
        "dg",
        capacity_kw=10,
        tech_min_pct=50,
        min_down_blocks=2,
        fuel_inr_per_kwh=5,
        initially_on=True,
        ramp_kw_per_hour=2,
    )
    s = check(P([8, 8, 8, 8], rate=[10, 1, 10, 10], thermals=[u]))
    # staying on through the cheap hour beats two hours off; the ramp keeps it at 6, not 5
    assert s.thermal["dg"] == pytest.approx([8, 6, 8, 8])


def test_thermal_must_run() -> None:
    u = Thermal("whr", capacity_kw=10, tech_min_pct=50, fuel_inr_per_kwh=5, must_run=True)
    s = check(P([8, 8], rate=1.0, thermals=[u]))
    assert s.thermal["whr"] == pytest.approx([5, 5])


def test_re_cap_of_contract_demand_binds() -> None:
    lim = Limit("re_cap_pct_of_contract_demand", 50, "RE cap", {"page": 1})
    s = check(P([10, 10, 10], [pv([1, 0.5, 0])], grid={"cd_kva": 10}, limits=[lim]))
    assert s.cap_kw["pv"] == pytest.approx(5)
    assert "limit:re_cap_pct_of_contract_demand:" in s.binding


@pytest.mark.parametrize(("minimum", "expected"), [(20, 20), (50, 0)])
def test_minimum_oa_size(minimum: float, expected: float) -> None:
    s = check(P([10, 10, 10], [pv([1, 0.5, 0], min_size_kw=minimum)]))
    assert s.cap_kw["pv"] == pytest.approx(expected)


def test_rooftop_curtails_and_respects_the_roof() -> None:
    roof = Candidate(
        "roof", shape=[1, 1, 0], energy_inr_per_kwh=[0, 0, 0], fixed_inr_per_kw_year=1, max_kw=100, btm=True
    )
    s = check(P([5, 20, 10], [roof], limits=[Limit("max_rooftop_kw", 12, "roof area", {}, target="roof")]))
    assert s.cap_kw["roof"] == pytest.approx(12)
    assert s.gen["roof"][0] == pytest.approx(5)  # curtailed to the load, never exported
    assert "limit:max_rooftop_kw:roof" in s.binding


def test_storage_mandate() -> None:
    b = Battery("bess", max_kw=100, min_hours=2, inr_per_kw_year=10)
    lim = Limit("storage_mandate_pct_of_re", 20, "storage mandate", {})
    s = check(P([10, 10, 10], [pv([1, 0.5, 0])], batteries=[b], limits=[lim]))
    assert s.bess_kw["bess"] == pytest.approx(0.2 * s.cap_kw["pv"])


def test_exchange_purchase_is_dispatched_block_by_block() -> None:
    iex = Candidate(
        "iex",
        shape=[1, 1, 1],
        energy_inr_per_kwh=[4, 9, 4],
        max_kw=50,
        category="exchange",
        dispatchable=True,
    )
    s = check(P([10, 10, 10], [iex], grid={"cd_kva": 0}))
    assert [round(x, 6) for x in s_delivered(s, "iex")] == [10, 0, 10]  # dearer than the grid at 9


def s_delivered(s: Solution, cid: str) -> list[float]:
    return s.delivered[cid]


def test_judge_prices_demand_slabs_and_excess_exactly() -> None:
    """GERC HTP-I: 500 kVA at 150, next 500 at 260, the rest at 475 (up to contract); 555 above it."""
    from dataclasses import replace

    from ergplan.optimizer.model import exact_of
    from ergplan.optimizer.resettle import demand_costs

    p = P([1200.0, 900.0], grid={"cd_kva": 1000.0, "pf": 1.0, "floor_pct": 85.0})
    x = replace(
        exact_of(p),
        demand_slabs={
            APR: [(Decimal(500), Decimal(150)), (Decimal(1000), Decimal(260)), (None, Decimal(475))]
        },
        excess_abs={APR: Decimal(555)},
        min_kva=Decimal(100),
        cd_kva=Decimal(1000),
    )
    p = replace(p, exact=x)
    out = demand_costs(p, [Decimal(1200), Decimal(900)], Decimal(1000))
    # billing demand 1200 kVA: 500 × 150 + 500 × 260 up to contract; 200 × 555 above it
    assert out == {"demand": Decimal(205000), "excess_demand": Decimal(111000)}
