"""Solve a built model with HiGHS (through Pyomo's highspy interface) and read the solution back.
Deterministic for the same problem and options (one thread), which the replay test relies on."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import highspy
import pyomo
import pyomo.environ as pyo
from pyomo.contrib.solver.common.factory import SolverFactory
from pyomo.contrib.solver.common.results import TerminationCondition

from .model import (
    Fixed,
    Netting,
    Problem,
    Start,
    build,
    build_settlement,
    chunk,
    coarsen,
    months_of,
    periods_of,
)

_HIGHS = getattr(highspy, "__version__", "1.15.1")
SOLVER_VERSION = f"highspy {_HIGHS} / pyomo {pyomo.__version__}"


class SolveFailed(RuntimeError):
    pass


@dataclass
class Solution:
    status: str
    objective: float
    gap: float | None
    seconds: float
    solver: str
    cap_kw: dict[str, float]
    bess_kw: dict[str, float]
    bess_kwh: dict[str, float]
    cd_kva: float
    delivered: dict[str, list[float]]  # OA candidate → kWh at the meter per block (must-take)
    gen: dict[str, list[float]]  # behind-the-meter candidate → kWh used per block
    charge: dict[str, list[float]]
    discharge: dict[str, list[float]]
    soc: dict[str, list[float]]
    thermal: dict[str, list[float]]
    metered: list[float]  # load net of behind-the-meter supply, per block
    md_kva: dict[date, float]
    settled: dict[date, dict[str, float]]  # the solver's own settlement, per month
    binding: list[str] = field(default_factory=list)


def _run(m: Any, time_limit_s: float, mip_gap: float) -> tuple[Any, float | None, bool]:
    opt = SolverFactory("highs")
    res = opt.solve(
        m,
        load_solutions=False,
        raise_exception_on_nonoptimal_result=False,
        time_limit=max(1.0, time_limit_s),
        solver_options={"threads": 1, "mip_rel_gap": mip_gap, "random_seed": 0, "output_flag": False},
    )
    tc = res.termination_condition
    if tc not in (
        TerminationCondition.convergenceCriteriaSatisfied,
        TerminationCondition.maxTimeLimit,
    ) or not res.solution_status.name.lower().startswith(("optimal", "feasible")):
        raise SolveFailed(f"solver ended with {tc.name} ({res.solution_status.name})")
    res.solution_loader.load_vars()
    gap = None
    if res.incumbent_objective is not None and res.objective_bound is not None:
        inc, bnd = float(res.incumbent_objective), float(res.objective_bound)
        gap = abs(inc - bnd) / max(1.0, abs(inc))
    return res, gap, tc == TerminationCondition.convergenceCriteriaSatisfied


def solve(p: Problem, time_limit_s: float = 120.0, mip_gap: float = 0.001) -> Solution:
    """Three passes.
    1. Sizing: capacities, contract demand and an hourly dispatch for the whole year (15-minute
       blocks are summed to hours), the bank guarded so it never takes energy the rule sets off first.
    2. Dispatch (15-minute problems only): sizes fixed, month by month at 15 minutes, carrying the
       battery's charge and the bank forward.
    3. Settlement: the dispatch fixed (read to the watt-hour, as the judge reads it), the solver
       settles it under the rule's order, banking period by banking period.
    The judge then settles the same dispatch again (optimizer.resettle)."""
    t0 = time.perf_counter()
    factor = 4 if p.hours == 0.25 else 1
    ps = coarsen(p, factor)
    m = build(ps)
    _, gap, optimal = _run(m, time_limit_s * 0.5, mip_gap)
    size = read(m, ps)
    objective = float(pyo.value(m.obj))
    binding_names = size.binding
    if factor == 1:
        sol = size
    else:
        fixed = Fixed(size.cap_kw, size.bess_kw, size.bess_kwh, size.cd_kva)
        start = Start(soc_kwh={b: v[-1] for b, v in size.soc.items()})
        parts: list[Solution] = []
        for idx in months_of(p):
            cp = chunk(p, idx, start, fixed)
            mc = build(cp)
            _run(mc, max(5.0, (time_limit_s * 0.8 - (time.perf_counter() - t0)) / 6), mip_gap)
            part = read(mc, cp)
            parts.append(part)
            start = Start(
                soc_kwh={b: v[-1] for b, v in part.soc.items()},
                bank_kwh=_carried(mc),
                on={u: v[-1] > 0 for u, v in part.thermal.items()},
            )
        sol = _merge(size, parts)
    sol.status = "optimal" if optimal else "time_limit"
    sol.objective = objective
    sol.gap = gap
    sol.binding = binding_names
    settled: dict[date, dict[str, float]] = {}
    start = Start()
    for idx in periods_of(p):
        cp = chunk(p, idx, start, None)
        ms = build_settlement(
            cp, [sol.metered[t] for t in idx], {k: [v[t] for t in idx] for k, v in sol.delivered.items()}
        )
        _run(ms, max(10.0, time_limit_s - (time.perf_counter() - t0)), 1e-9)
        for mo, row in read_settlement(ms, cp).items():
            settled[mo] = row
        start = Start(bank_kwh=_carried(ms))
    sol.settled = settled
    sol.seconds = time.perf_counter() - t0
    return sol


def _carried(m: Any) -> dict[str, float]:
    """Bank balance carried out of a chunk: the last step's inventory less what lapsed there."""
    net: Netting = m.netting
    if not net.buckets or net.steps == 0:
        return {}
    last = net.steps - 1
    out = {}
    for bk in net.buckets:
        v = _v(m.inv[bk, last])
        if last in net.step_period_end:
            v -= _v(m.lapse[bk, net.period_of_step[last]])
        out[bk] = max(0.0, v)
    return out


def _merge(size: Solution, parts: list[Solution]) -> Solution:
    def cat(get: Any) -> dict[str, list[float]]:
        keys = get(parts[0]).keys()
        return {k: [x for pt in parts for x in get(pt)[k]] for k in keys}

    md: dict[date, float] = {}
    for pt in parts:
        md.update(pt.md_kva)
    return Solution(
        status="",
        objective=0.0,
        gap=None,
        seconds=0.0,
        solver=size.solver,
        cap_kw=size.cap_kw,
        bess_kw=size.bess_kw,
        bess_kwh=size.bess_kwh,
        cd_kva=size.cd_kva,
        delivered=cat(lambda s: s.delivered),
        gen=cat(lambda s: s.gen),
        charge=cat(lambda s: s.charge),
        discharge=cat(lambda s: s.discharge),
        soc=cat(lambda s: s.soc),
        thermal=cat(lambda s: s.thermal),
        metered=[x for pt in parts for x in pt.metered],
        md_kva=md,
        settled={},
    )


def _v(x: Any) -> float:
    v = pyo.value(x, exception=False)
    return 0.0 if v is None or abs(v) < 1e-9 else float(v)


def read(m: Any, p: Problem) -> Solution:
    n = p.n
    cap = {c.id: _v(m.cap[c.id]) for c in p.candidates}
    xv = m.x.extract_values()
    r3 = _r3
    delivered = {
        c.id: (
            [r3(_clean(xv.get((c.id, t)))) for t in range(n)]
            if c.dispatchable
            else [r3(cap[c.id] * c.shape[t]) for t in range(n)]
        )
        for c in p.candidates
        if not c.btm
    }
    gvals = m.gen.extract_values()
    gen = {c.id: [_clean(gvals.get((c.id, t))) for t in range(n)] for c in p.candidates if c.btm}
    ch = {b.id: _series(m.ch, b.id, n) for b in p.batteries}
    dis = {b.id: _series(m.dis, b.id, n) for b in p.batteries}
    soc = {b.id: _series(m.soc, b.id, n) for b in p.batteries}
    th = {u.id: _series(m.out, u.id, n) for u in p.thermals}
    metered = []
    for t in range(n):
        v = p.load_kwh[t]
        v -= sum(g[t] for g in gen.values())
        v -= sum(d[t] for d in dis.values())
        v += sum(c[t] for c in ch.values())
        v -= sum(o[t] for o in th.values())
        metered.append(r3(max(0.0, v)))
    md = {mo: _v(m.md[mo]) for mo in m.md}
    sol = Solution(
        status="",
        objective=0.0,
        gap=None,
        seconds=0.0,
        solver=SOLVER_VERSION,
        cap_kw=cap,
        bess_kw={b.id: _v(m.bkw[b.id]) for b in p.batteries},
        bess_kwh={b.id: _v(m.bkwh[b.id]) for b in p.batteries},
        cd_kva=float(pyo.value(m.cd_expr)),
        delivered=delivered,
        gen=gen,
        charge=ch,
        discharge=dis,
        soc=soc,
        thermal=th,
        metered=metered,
        md_kva=md,
        settled={},
    )
    sol.binding = binding(m, p)
    return sol


def read_settlement(m: Any, p: Problem) -> dict[date, dict[str, float]]:
    """The solver's settlement per month, from a settlement-pass model."""
    net: Netting = m.netting
    # the solver's settlement per month
    settled: dict[date, dict[str, float]] = defaultdict(
        lambda: {"grid": 0.0, "setoff": 0.0, "withdrawn": 0.0, "banked": 0.0, "charge": 0.0, "lapsed": 0.0}
    )
    so, dep, w, grid = (
        m.so.extract_values(),
        m.dep.extract_values(),
        m.w.extract_values(),
        m.grid.extract_values(),
    )
    keep = 1 - net.charge_pct / 100
    for g, idx in enumerate(net.groups):
        mo = p.blocks[idx[0]].month
        settled[mo]["grid"] += _clean(grid.get(g))
    for (_k, g), v in so.items():
        settled[p.blocks[net.groups[g][0]].month]["setoff"] += _clean(v)
    for (_k, g), v in dep.items():
        mo = p.blocks[net.groups[g][0]].month
        settled[mo]["banked"] += keep * _clean(v)
        settled[mo]["charge"] += (1 - keep) * _clean(v)
    for (_b, g), v in w.items():
        settled[p.blocks[net.groups[g][0]].month]["withdrawn"] += _clean(v)
    step_month: dict[int, date] = {}
    for g, idx in enumerate(net.groups):
        step_month[net.group_step[g]] = p.blocks[idx[0]].month
    period_end_month = {net.period_of_step[s]: step_month[s] for s in net.step_period_end if s in step_month}
    for (_b, q), v in m.lapse.extract_values().items():
        if q in period_end_month:
            settled[period_end_month[q]]["lapsed"] += _clean(v)
    return dict(settled)


def _r3(x: float) -> float:
    return float(f"{x:.3f}")


def _clean(v: Any) -> float:
    if v is None:
        return 0.0
    f = float(v)
    return 0.0 if abs(f) < 1e-9 else f


def _series(var: Any, key: str, n: int) -> list[float]:
    vals = var.extract_values()
    return [_clean(vals.get((key, t))) for t in range(n)]


def binding(m: Any, p: Problem, tol: float = 1e-4) -> list[str]:
    """Names of constraints and bounds that hold the solution where it is."""
    out: list[str] = []
    for c in p.candidates:
        v = _v(m.cap[c.id])
        if c.max_kw > 0 and v >= c.max_kw * (1 - tol):
            out.append(f"max_kw:{c.id}")
        if c.min_size_kw > 0 and abs(v - c.min_size_kw) <= c.min_size_kw * tol:
            out.append(f"min_size:{c.id}")
    for b in p.batteries:
        if b.max_kw > 0 and _v(m.bkw[b.id]) >= b.max_kw * (1 - tol):
            out.append(f"max_kw:{b.id}")
    for i, name in m.cons_names.items():
        if not name.startswith(("limit:", "carry_cap", "cd_floor")):
            continue
        c = m.cons[i]
        body = pyo.value(c.body, exception=False)
        if body is None:
            continue
        scale = max(1.0, abs(body))
        hit = (c.upper is not None and abs(pyo.value(c.upper) - body) <= tol * scale) or (
            c.lower is not None and abs(pyo.value(c.lower) - body) <= tol * scale
        )
        if hit:
            out.append(name)
    return sorted(set(out))
