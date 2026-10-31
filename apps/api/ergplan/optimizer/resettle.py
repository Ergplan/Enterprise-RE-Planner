"""The optimizer never has the last word (invariant 6): the solver's dispatch is settled again by
`settlement.simulate()`, the judge. Settled quantities are compared month by month; a disagreement
above the tolerance fails the run. Costs reported to a client come from the re-settled quantities,
never from the solver's objective."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..settlement.simulate import Block, Result, SourceIn, simulate
from .highs_solve import Solution
from .model import Problem

QUANTITIES = ("grid", "setoff", "withdrawn", "banked", "charge", "lapsed")
KWH = Decimal("0.001")
INR = Decimal("0.01")


def dec(x: float) -> Decimal:
    """A solver float as a Decimal, rounded to the watt-hour (deterministic for the same float)."""
    return Decimal(f"{x:.3f}")


@dataclass
class Resettled:
    agrees: bool
    max_diff_kwh: Decimal
    by_month: dict[date, dict[str, dict[str, Decimal]]]  # month → quantity → {solver, settled}
    result: Result
    blocks: list[Block]
    costs: dict[str, Decimal] = field(default_factory=dict)  # annual INR by line, re-settled


def blocks_for(p: Problem, sol: Solution) -> list[Block]:
    out = []
    for t, b in enumerate(p.blocks):
        out.append(
            Block(
                month=b.month,
                slot=b.slot,
                classes=b.classes,
                hour=b.hour,
                load_kwh=dec(sol.metered[t]),
                supply_kwh={k: dec(v[t]) for k, v in sol.delivered.items()},
            )
        )
    return out


def resettle(p: Problem, sol: Solution, tolerance_kwh: Decimal) -> Resettled:
    blocks = blocks_for(p, sol)
    sources = [SourceIn(id=c.id, category=c.category, may_bank=c.may_bank) for c in p.candidates if not c.btm]
    res = simulate(blocks, sources, p.rule)
    sim: dict[date, dict[str, Decimal]] = defaultdict(lambda: {q: Decimal(0) for q in QUANTITIES})
    for i, b in enumerate(blocks):
        s = sim[b.month]
        s["grid"] += res.grid_kwh[i]
        s["withdrawn"] += res.withdrawn_kwh[i]
        s["setoff"] += sum((v[i] for v in res.setoff_kwh.values()), Decimal(0))
        s["banked"] += sum((v[i] for v in res.deposit_kwh.values()), Decimal(0))
        s["charge"] += sum((v[i] for v in res.charge_kwh.values()), Decimal(0))
    for x in res.lapsed:
        sim[x["month"]]["lapsed"] += x["kwh"]
    by_month: dict[date, dict[str, dict[str, Decimal]]] = {}
    worst = Decimal(0)
    for mo in sorted(sim):
        row = {}
        for q in QUANTITIES:
            a = dec(sol.settled.get(mo, {}).get(q, 0.0))
            b2 = sim[mo][q].quantize(KWH)
            row[q] = {"solver": a, "settled": b2}
            worst = max(worst, abs(a - b2))
        by_month[mo] = row
    for q in QUANTITIES:  # annual totals too
        a = sum((r[q]["solver"] for r in by_month.values()), Decimal(0))
        b2 = sum((r[q]["settled"] for r in by_month.values()), Decimal(0))
        worst = max(worst, abs(a - b2))
    out = Resettled(
        agrees=worst <= tolerance_kwh,
        max_diff_kwh=worst.quantize(KWH),
        by_month=by_month,
        result=res,
        blocks=blocks,
    )
    out.costs = costs(p, sol, res, blocks)
    return out


def costs(p: Problem, sol: Solution, res: Result, blocks: list[Block]) -> dict[str, Decimal]:
    """Annual INR by line at the solver's sizes and the judge's settlement."""
    d = Decimal
    c: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for cand in p.candidates:
        cap = dec(sol.cap_kw[cand.id])
        if cand.fixed_inr_per_kw_year:
            c[f"fixed:{cand.id}"] += cap * d(str(cand.fixed_inr_per_kw_year))
        series = sol.gen[cand.id] if cand.btm else sol.delivered[cand.id]
        c[f"energy:{cand.id}"] += sum(
            (dec(series[t]) * d(str(cand.energy_inr_per_kwh[t])) for t in range(p.n) if series[t]),
            Decimal(0),
        )
    c["grid_energy"] = sum((res.grid_kwh[t] * d(str(p.grid.rate[t])) for t in range(p.n)), Decimal(0))
    for b in p.batteries:
        c[f"fixed:{b.id}"] += dec(sol.bess_kw[b.id]) * d(str(b.inr_per_kw_year)) + dec(
            sol.bess_kwh[b.id]
        ) * d(str(b.inr_per_kwh_year))
    for u in p.thermals:
        c[f"energy:{u.id}"] += sum((dec(x) for x in sol.thermal[u.id]), Decimal(0)) * d(
            str(u.fuel_inr_per_kwh)
        )
    c.update(demand_costs(p, [b.load_kwh for b in blocks], dec(sol.cd_kva)))
    if p.grid.cd_step_kva:
        c["cd_change"] = abs(dec(sol.cd_kva) - d(str(p.grid.cd_kva))) * d(
            str(p.grid.cd_change_inr_per_kva_year)
        )
    ch = ((p.rule.body.get("banking") or {}).get("charge") or {}) if p.rule else {}
    if ch.get("kind") == "inr_per_kwh" and ch.get("value"):
        gross = sum((sum(v, Decimal(0)) for v in res.deposit_kwh.values()), Decimal(0)) + sum(
            (sum(v, Decimal(0)) for v in res.charge_kwh.values()), Decimal(0)
        )
        c["banking_charge"] = gross * d(str(ch["value"]))
    if p.lapse_inr_per_kwh:
        c["lapse_payment"] = -sum((x["kwh"] for x in res.lapsed), Decimal(0)) * d(str(p.lapse_inr_per_kwh))
    return {k: v.quantize(INR) for k, v in c.items()}


def demand_costs(p: Problem, metered_kwh: list[Decimal], cd_kva: Decimal) -> dict[str, Decimal]:
    """Demand and excess-demand charges for a year of metered drawal (kWh per block)."""
    d = Decimal
    gr = p.grid
    by_month: dict[date, Decimal] = defaultdict(lambda: Decimal(0))
    per_kva = d(str(p.hours)) * d(str(gr.pf))
    for t, b in enumerate(p.blocks):
        by_month[b.month] = max(by_month[b.month], metered_kwh[t] / per_kva)
    out = {"demand": Decimal(0), "excess_demand": Decimal(0)}
    floor = cd_kva * d(str(gr.floor_pct)) / 100
    for mo, md in by_month.items():
        out["demand"] += max(md, floor) * d(str(gr.demand_rate.get(mo, 0.0)))
        out["excess_demand"] += max(md - cd_kva, Decimal(0)) * d(str(gr.excess_rate.get(mo, 0.0)))
    return out


def status_quo(p: Problem) -> dict[str, Decimal]:
    """The year's grid cost with nothing built: every kWh from the DISCOM."""
    d = Decimal
    loads = [dec(x) for x in p.load_kwh]
    out = {"grid_energy": sum((loads[t] * d(str(p.grid.rate[t])) for t in range(p.n)), Decimal(0))}
    out.update(demand_costs(p, loads, d(str(p.grid.cd_kva))))
    return {k: v.quantize(INR) for k, v in out.items()}
