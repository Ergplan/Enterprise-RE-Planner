"""The sizing and dispatch MILP (Stage 6). Pure: a `Problem` in, a Pyomo model out; `highs_solve`
solves it. No database, no model SDK, no network.

One representative year of blocks (35,040 at 15 minutes, or 8,760 hourly for a preview).

Variables
- capacity per candidate source (kW; OA sources must-take at capacity × shape, behind-the-meter
  generation may be curtailed); a binary "built" where a regulatory minimum size applies;
- battery power (kW) and energy (kWh); charge, discharge and state of charge per block;
- thermal output per block with on/off, start-up and shut-down binaries;
- settlement per netting unit of the approved rule: set-off per source, deposits (gross of the
  charge in kind), unbanked surplus, withdrawals per bucket, grid energy; bank inventory per bucket
  with drawal-window masks, lapse at each banking period's end, the carry-over ceiling;
- recorded demand and billing demand per month; contract demand as a step variable with a change cost.

Objective: annual INR = Σ fixed costs × capacity + Σ landed energy cost × delivered energy
+ grid energy at the avoided-cost rate + demand and excess-demand charges + banking charges in INR
+ thermal fuel and start-ups + contract-demand change − payment for lapsed energy.

The bank follows `settlement.simulate.Bank` (the same bucket and window logic), so the solver and
the judge read the rule the same way; the judge still re-settles every result (invariant 6).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pyomo.environ as pyo

from ..rulebook.models import RuleView
from ..settlement.simulate import Bank, _period_index

AGGREGATED = ("tod_slot_monthly", "monthly_aggregate", "annual")


@dataclass(frozen=True)
class BlockMeta:
    month: date  # first of the month
    slot: str
    classes: frozenset[str] = frozenset()
    hour: int = 0


@dataclass(frozen=True)
class Grid:
    """The DISCOM supply the plan displaces."""

    rate: list[float]  # INR/kWh per block: the avoided energy cost (ToD-adjusted, with duties)
    demand_rate: dict[date, float]  # INR/kVA/month on billing demand
    floor_pct: float = 0.0  # billing demand ≥ this % of contract demand
    excess_rate: dict[date, float] = field(default_factory=dict)  # INR/kVA/month above contract demand
    cd_kva: float = 0.0
    pf: float = 0.95  # kW → kVA for recorded demand
    cd_step_kva: float | None = None  # contract demand as a step variable when set
    cd_min_kva: float = 0.0
    cd_max_kva: float | None = None
    cd_change_inr_per_kva_year: float = 0.0


@dataclass(frozen=True)
class Candidate:
    id: str
    shape: list[float]  # kWh at the meter per kW of capacity, per block (losses applied)
    energy_inr_per_kwh: list[float]  # landed cost per kWh at the meter, per block (0 for owned BTM)
    fixed_inr_per_kw_year: float = 0.0  # CRF × capex + O&M for owned plant
    min_kw: float = 0.0
    max_kw: float = 0.0
    category: str = "captive_generation"  # captive_generation | bilateral | exchange
    btm: bool = False  # behind the meter: lowers the metered drawal, may be curtailed
    may_bank: bool = False
    renewable: bool = True
    min_size_kw: float = 0.0  # a regulatory minimum if built (binary)
    dispatchable: bool = False  # an OA purchase scheduled block by block (exchange), not must-take


@dataclass(frozen=True)
class Battery:
    id: str
    max_kw: float
    min_kw: float = 0.0
    min_hours: float = 1.0
    max_hours: float = 4.0
    eff_charge: float = 0.95
    eff_discharge: float = 0.95
    inr_per_kw_year: float = 0.0
    inr_per_kwh_year: float = 0.0


@dataclass(frozen=True)
class Thermal:
    id: str
    capacity_kw: float
    tech_min_pct: float = 0.0
    ramp_kw_per_hour: float | None = None
    min_up_blocks: int = 1
    min_down_blocks: int = 1
    must_run: bool = False
    fuel_inr_per_kwh: float = 0.0
    start_inr: float = 0.0
    initially_on: bool = False


@dataclass(frozen=True)
class Limit:
    """A regulatory or client limit; `ref` travels to the binding-constraint list."""

    kind: str  # re_cap_pct_of_contract_demand | storage_mandate_pct_of_re | … | max_rooftop_kw | max_kw
    value: float
    label: str
    ref: dict[str, Any] = field(default_factory=dict)
    target: str | None = None  # candidate id for per-source limits


@dataclass(frozen=True)
class Start:
    soc_kwh: dict[str, float] = field(default_factory=dict)
    bank_kwh: dict[str, float] = field(default_factory=dict)
    on: dict[str, bool] = field(default_factory=dict)
    # the banking period's injection and grid drawal so far, when a period spans chunks
    period_injection_kwh: float = 0.0
    period_grid_kwh: float = 0.0


@dataclass(frozen=True)
class Fixed:
    cap_kw: dict[str, float]
    bess_kw: dict[str, float]
    bess_kwh: dict[str, float]
    cd_kva: float


@dataclass(frozen=True)
class Problem:
    blocks: list[BlockMeta]
    hours: float  # length of a block in hours (0.25 or 1)
    load_kwh: list[float]
    grid: Grid
    candidates: list[Candidate] = field(default_factory=list)
    batteries: list[Battery] = field(default_factory=list)
    thermals: list[Thermal] = field(default_factory=list)
    rule: RuleView | None = None
    limits: list[Limit] = field(default_factory=list)
    lapse_inr_per_kwh: float = 0.0
    big_m_kwh: float | None = None
    next_month: date | None = None  # the month after the last block when the year goes on (a chunk)
    start: Start | None = None  # state carried in from the previous chunk; None: a whole, cyclic year
    fixed: Fixed | None = None  # sizes fixed (a dispatch pass)

    @property
    def n(self) -> int:
        return len(self.blocks)


# ---------------------------------------------------------------- netting structure


@dataclass
class Netting:
    """Netting units (groups of blocks), the bank's steps and periods, built from the rule."""

    granularity: str
    groups: list[list[int]]  # block indices per netting unit, in time order
    group_step: list[int]  # step index of each group (deposits before withdrawals within a step)
    steps: int
    step_period_end: dict[int, tuple[bool, bool]]  # step → (banking period ends, financial year ends)
    period_of_step: list[int]
    deposit_bucket: list[str | None]  # bucket a deposit in this group goes to
    drawable: list[list[str]]  # buckets this group may draw on
    buckets: list[str]
    charge_pct: float
    charge_inr: float
    carry: bool
    cap: dict[str, Any]
    banking: bool


def netting(p: Problem) -> Netting:
    body = p.rule.body if p.rule else {}
    gran = str(body.get("granularity", "block_15min"))
    banking = body.get("banking") or {}
    bank = Bank(p.rule)
    keys: dict[tuple[Any, ...], list[int]] = {}
    for i, b in enumerate(p.blocks):
        if gran == "hourly":
            k: tuple[Any, ...] = (b.month, b.hour)
        elif gran == "tod_slot_monthly":
            k = (b.month, b.slot)
        elif gran == "monthly_aggregate":
            k = (b.month,)
        elif gran == "annual":
            k = (_period_index(b.month, "financial_year"),)
        else:
            k = (i,)
        keys.setdefault(k, []).append(i)
    groups = sorted(keys.values(), key=lambda idx: idx[0])
    # steps: each group for block / hourly netting, each month for aggregated netting
    group_step: list[int] = []
    step_month: list[date] = []
    last: Any = None
    for idx in groups:
        m = p.blocks[idx[0]].month
        key = m if gran in AGGREGATED else idx[0]
        if key != last:
            step_month.append(m)
            last = key
        group_step.append(len(step_month) - 1)
    period_kind = str(banking.get("period", "monthly"))
    ends: dict[int, tuple[bool, bool]] = {}
    for s, m in enumerate(step_month):
        nxt = step_month[s + 1] if s + 1 < len(step_month) else p.next_month
        pe = nxt is None or _period_index(nxt, period_kind) != _period_index(m, period_kind)
        fe = nxt is None or _period_index(nxt, "financial_year") != _period_index(m, "financial_year")
        if pe or fe:
            ends[s] = (pe, fe)
    period_of_step = []
    pidx = 0
    for s in range(len(step_month)):
        period_of_step.append(pidx)
        if s in ends:
            pidx += 1
    dep_b: list[str | None] = []
    draw: list[list[str]] = []
    for idx in groups:
        b0 = p.blocks[idx[0]]
        dep_b.append(bank.bucket_for(b0.slot, b0.classes, b0.month.month))
    buckets = sorted({b for b in dep_b if b is not None})
    for idx in groups:
        b0 = p.blocks[idx[0]]
        if not bank.windows:
            draw.append(list(buckets))
            continue
        draw.append([k for k in bank.drawable(b0.slot, b0.classes, b0.month.month) if k in buckets])
    ch = banking.get("charge") or {}
    return Netting(
        granularity=gran,
        groups=groups,
        group_step=group_step,
        steps=len(step_month),
        step_period_end=ends,
        period_of_step=period_of_step,
        deposit_bucket=dep_b,
        drawable=draw,
        buckets=buckets,
        charge_pct=float(bank.charge_pct()),
        charge_inr=float(ch["value"]) if ch.get("kind") == "inr_per_kwh" and ch.get("value") else 0.0,
        carry=bool(banking.get("carry_over")),
        cap=dict(banking.get("cap") or {}),
        banking=bank.allowed,
    )


# ---------------------------------------------------------------- model


def build(p: Problem) -> pyo.ConcreteModel:
    n = p.n
    T = range(n)
    h = p.hours
    net = netting(p)
    m = pyo.ConcreteModel(name="ergplan")
    m.netting = net  # kept for reading the solution
    m.problem = p
    cands = p.candidates
    oa = [c for c in cands if not c.btm]
    btm = [c for c in cands if c.btm]
    nonneg = pyo.NonNegativeReals

    # capacities
    m.cap = pyo.Var([c.id for c in cands], within=nonneg)
    built_needed = [c for c in cands if c.min_size_kw > 0]
    m.built = pyo.Var([c.id for c in built_needed], within=pyo.Binary)
    m.cons = pyo.ConstraintList()
    names: dict[int, str] = {}

    def add(expr: Any, name: str | None = None) -> None:
        if isinstance(expr, bool):  # a constant row (e.g. a block with nothing behind the meter)
            if not expr:
                raise ValueError(f"infeasible constant constraint {name or ''}")
            return
        m.cons.add(expr)
        if name:
            names[len(m.cons)] = name

    for c in cands:
        m.cap[c.id].setlb(c.min_kw)
        m.cap[c.id].setub(c.max_kw)
    for c in built_needed:
        add(m.cap[c.id] >= c.min_size_kw * m.built[c.id], f"min_size:{c.id}")
        add(m.cap[c.id] <= c.max_kw * m.built[c.id])
    if p.fixed is not None:
        for c in cands:
            m.cap[c.id].fix(p.fixed.cap_kw.get(c.id, 0.0))
        for c in built_needed:
            m.built[c.id].fix(1 if p.fixed.cap_kw.get(c.id, 0.0) > 0 else 0)

    # behind-the-meter generation (curtailable)
    btm_ids = [c.id for c in btm]
    m.gen = pyo.Var([(k, t) for k in btm_ids for t in T if _shape(cands, k)[t] > 0], within=nonneg)
    for c in btm:
        for t in T:
            if c.shape[t] > 0:
                add(m.gen[c.id, t] <= c.shape[t] * m.cap[c.id])

    # batteries
    bids = [b.id for b in p.batteries]
    m.bkw = pyo.Var(bids, within=nonneg)
    m.bkwh = pyo.Var(bids, within=nonneg)
    m.ch = pyo.Var([(b, t) for b in bids for t in T], within=nonneg)
    m.dis = pyo.Var([(b, t) for b in bids for t in T], within=nonneg)
    m.soc = pyo.Var([(b, t) for b in bids for t in T], within=nonneg)
    for b in p.batteries:
        m.bkw[b.id].setlb(b.min_kw)
        m.bkw[b.id].setub(b.max_kw)
        if p.fixed is not None:
            m.bkw[b.id].fix(p.fixed.bess_kw.get(b.id, 0.0))
            m.bkwh[b.id].fix(p.fixed.bess_kwh.get(b.id, 0.0))
        add(m.bkwh[b.id] >= b.min_hours * m.bkw[b.id], f"bess_min_hours:{b.id}")
        add(m.bkwh[b.id] <= b.max_hours * m.bkw[b.id])
        if p.start is not None and n > 0:
            add(m.soc[b.id, n - 1] >= p.start.soc_kwh.get(b.id, 0.0))  # a chunk leaves what it found
        for t in T:
            if t > 0:
                prev: Any = m.soc[b.id, t - 1]
            elif p.start is None:
                prev = m.soc[b.id, n - 1]  # a whole year: cyclic
            else:
                prev = p.start.soc_kwh.get(b.id, 0.0)
            add(m.soc[b.id, t] == prev + b.eff_charge * m.ch[b.id, t] - m.dis[b.id, t] / b.eff_discharge)
            add(m.soc[b.id, t] <= m.bkwh[b.id])
            add(m.ch[b.id, t] <= h * m.bkw[b.id])
            add(m.dis[b.id, t] <= h * m.bkw[b.id])

    # thermal units
    tids = [u.id for u in p.thermals]
    m.out = pyo.Var([(u, t) for u in tids for t in T], within=nonneg)
    m.on = pyo.Var([(u, t) for u in tids for t in T], within=pyo.Binary)
    m.su = pyo.Var([(u, t) for u in tids for t in T], within=nonneg, bounds=(0, 1))
    m.sd = pyo.Var([(u, t) for u in tids for t in T], within=nonneg, bounds=(0, 1))
    for u in p.thermals:
        cap_blk = u.capacity_kw * h
        for t in T:
            add(m.out[u.id, t] <= cap_blk * m.on[u.id, t])
            add(m.out[u.id, t] >= u.tech_min_pct / 100 * cap_blk * m.on[u.id, t], f"tech_min:{u.id}")
            on0 = p.start.on.get(u.id, u.initially_on) if p.start else u.initially_on
            prev_on: Any = (1 if on0 else 0) if t == 0 else m.on[u.id, t - 1]
            add(m.on[u.id, t] - prev_on == m.su[u.id, t] - m.sd[u.id, t])
            if u.must_run:
                m.on[u.id, t].fix(1)
            if u.ramp_kw_per_hour is not None and t > 0:
                r = u.ramp_kw_per_hour * h * h  # kW per hour × hours → kW change per block, × h → kWh
                add(m.out[u.id, t] - m.out[u.id, t - 1] <= r + cap_blk * m.su[u.id, t], f"ramp:{u.id}")
                add(m.out[u.id, t - 1] - m.out[u.id, t] <= r + cap_blk * m.sd[u.id, t], f"ramp:{u.id}")
            if u.min_up_blocks > 1:
                lo = max(0, t - u.min_up_blocks + 1)
                add(sum(m.su[u.id, j] for j in range(lo, t + 1)) <= m.on[u.id, t], f"min_up:{u.id}")
            if u.min_down_blocks > 1:
                lo = max(0, t - u.min_down_blocks + 1)
                add(sum(m.sd[u.id, j] for j in range(lo, t + 1)) <= 1 - m.on[u.id, t], f"min_down:{u.id}")

    # metered drawal per block (load net of behind-the-meter supply), never an export
    def metered(t: int) -> Any:
        e: Any = p.load_kwh[t]
        for c in btm:
            if c.shape[t] > 0:
                e = e - m.gen[c.id, t]
        for b in bids:
            e = e - m.dis[b, t] + m.ch[b, t]
        for u in tids:
            e = e - m.out[u, t]
        return e

    has_btm = bool(btm or bids or tids)
    if has_btm:
        for t in T:
            add(metered(t) >= 0)

    # dispatchable open-access purchases (exchange): scheduled per block up to capacity × shape
    disp = [c for c in oa if c.dispatchable]
    m.x = pyo.Var([(c.id, t) for c in disp for t in T if c.shape[t] > 0], within=nonneg)
    for c in disp:
        for t in T:
            if c.shape[t] > 0:
                add(m.x[c.id, t] <= c.shape[t] * m.cap[c.id])

    # settlement (sizing mode: the bank may not take energy the rule would set off directly — see guard)
    oa_by = {c.id: c for c in oa}
    S = {c.id: [sum(c.shape[t] for t in idx) for idx in net.groups] for c in oa}

    def supplied(k: str, g: int) -> Any:
        c = oa_by[k]
        if c.dispatchable:
            return sum(m.x[k, t] for t in net.groups[g] if c.shape[t] > 0)
        return S[k][g] * m.cap[k]

    def group_load(g: int) -> Any:
        idx = net.groups[g]
        return sum(metered(t) for t in idx) if has_btm else sum(p.load_kwh[t] for t in idx)

    settle_cost = _settlement(
        m, p, net, add, group_load, supplied, {k: [v > 0 for v in S[k]] for k in S}, "size"
    )

    # demand
    months = sorted({b.month for b in p.blocks})
    m.md = pyo.Var(months, within=nonneg)
    m.bd = pyo.Var(months, within=nonneg)
    m.ex = pyo.Var(months, within=nonneg)
    gr = p.grid
    if p.fixed is not None:
        cd: Any = p.fixed.cd_kva
    elif gr.cd_step_kva:
        lo = int(gr.cd_min_kva // gr.cd_step_kva)
        hi = int((gr.cd_max_kva or gr.cd_kva) // gr.cd_step_kva)
        m.cd_steps = pyo.Var(within=pyo.Integers, bounds=(lo, hi))
        cd = gr.cd_step_kva * m.cd_steps
        m.cd_up = pyo.Var(within=nonneg)
        m.cd_dn = pyo.Var(within=nonneg)
        add(cd - gr.cd_kva == m.cd_up - m.cd_dn)
    else:
        cd = gr.cd_kva
    m.cd_expr = cd
    by_month: dict[date, list[int]] = defaultdict(list)
    for t, blk in enumerate(p.blocks):
        by_month[blk.month].append(t)
    for mo, idx in by_month.items():
        if has_btm:
            for t in idx:
                add(m.md[mo] >= metered(t) / (h * gr.pf))
        else:
            m.md[mo].fix(max(p.load_kwh[t] for t in idx) / (h * gr.pf))
        add(m.bd[mo] >= m.md[mo])
        add(m.bd[mo] >= gr.floor_pct / 100 * cd, "cd_floor")
        add(m.ex[mo] >= m.md[mo] - cd)

    # limits
    re_caps = [m.cap[c.id] for c in oa if c.renewable]
    for lim in p.limits:
        tag = f"limit:{lim.kind}:{lim.target or ''}"
        if lim.kind == "re_cap_pct_of_contract_demand" and re_caps:
            add(sum(re_caps) <= lim.value / 100 * cd, tag)
        elif lim.kind == "storage_mandate_pct_of_re" and bids:
            add(sum(m.bkw[bid] for bid in bids) >= lim.value / 100 * sum(re_caps), tag)
        elif lim.kind == "storage_mandate_pct_of_contract_demand" and bids:
            add(sum(m.bkw[bid] for bid in bids) >= lim.value / 100 * cd, tag)
        elif lim.kind == "min_bess_hours":
            for bid in bids:
                add(m.bkwh[bid] >= lim.value * m.bkw[bid], tag)
        elif lim.kind == "min_contract_demand_for_oa_kva" and oa:
            m.oa_on = pyo.Var(within=pyo.Binary)
            add(sum(m.cap[c.id] for c in oa) <= sum(c.max_kw for c in oa) * m.oa_on)
            add(cd >= lim.value * m.oa_on, tag)
        elif lim.kind in ("max_kw", "max_rooftop_kw") and lim.target in m.cap:
            add(m.cap[lim.target] <= lim.value, tag)

    # objective
    obj: Any = 0
    for c in cands:
        obj += c.fixed_inr_per_kw_year * m.cap[c.id]
    for c in oa:
        if c.dispatchable:
            obj += sum(c.energy_inr_per_kwh[t] * m.x[c.id, t] for t in T if c.shape[t] > 0)
        else:
            obj += sum(c.shape[t] * c.energy_inr_per_kwh[t] for t in T) * m.cap[c.id]
    for c in btm:
        for t in T:
            if c.shape[t] > 0 and c.energy_inr_per_kwh[t]:
                obj += c.energy_inr_per_kwh[t] * m.gen[c.id, t]
    obj += settle_cost
    for b in p.batteries:
        obj += b.inr_per_kw_year * m.bkw[b.id] + b.inr_per_kwh_year * m.bkwh[b.id]
    for u in p.thermals:
        obj += sum(u.fuel_inr_per_kwh * m.out[u.id, t] + u.start_inr * m.su[u.id, t] for t in T)
    for mo in months:
        obj += gr.demand_rate.get(mo, 0.0) * m.bd[mo] + gr.excess_rate.get(mo, 0.0) * m.ex[mo]
    if gr.cd_step_kva and p.fixed is None:
        obj += gr.cd_change_inr_per_kva_year * (m.cd_up + m.cd_dn)
    m.obj = pyo.Objective(expr=obj, sense=pyo.minimize)
    m.cons_names = names
    return m


def _settlement(
    m: Any,
    p: Problem,
    net: Netting,
    add: Any,
    group_load: Any,
    supplied: Any,
    has_supply: dict[str, list[bool]],
    mode: str,
) -> Any:
    """Settlement variables and rows, shared by the sizing model and the settlement pass.

    `size`: the objective is money (grid energy at the avoided-cost rate, INR banking charges,
    payment for lapsed energy) plus a guard on deposits: banking a kWh costs at least what the bank
    could earn over setting it off in its own block, so the solver never banks energy the rule
    would set off directly (set-off comes first, Reg. order). The carry-over ceiling takes the lower
    of two ceilings (linear, conservative).
    `settle`: the dispatch is fixed; the objective imposes the rule's order — direct set-off first,
    then withdrawals as early as the windows allow (in the rule's bucket priority), then the least
    lapse under the ceiling (the higher of two ceilings exactly, by a binary per period)."""
    G = range(len(net.groups))
    ks = list(has_supply)
    m.so = pyo.Var([(k, g) for k in ks for g in G if has_supply[k][g]], within=pyo.NonNegativeReals)
    bankable = [
        (k, g)
        for k in ks
        for g in G
        if has_supply[k][g] and _may_bank(p, k) and net.deposit_bucket[g] is not None
    ]
    m.dep = pyo.Var(bankable, within=pyo.NonNegativeReals)
    m.unb = pyo.Var([(k, g) for k in ks for g in G if has_supply[k][g]], within=pyo.NonNegativeReals)
    draw_idx = [(bk, g) for g in G for bk in net.drawable[g]] if net.banking else []
    m.w = pyo.Var(draw_idx, within=pyo.NonNegativeReals)
    m.grid = pyo.Var(list(G), within=pyo.NonNegativeReals)
    dep_set = set(bankable)
    for g in G:
        terms: Any = m.grid[g]
        for k in ks:
            if has_supply[k][g]:
                terms = terms + m.so[k, g]
                use: Any = m.so[k, g] + m.unb[k, g]
                if (k, g) in dep_set:
                    use = use + m.dep[k, g]
                add(use == supplied(k, g))
        for bk in net.drawable[g] if net.banking else []:
            terms = terms + m.w[bk, g]
        add(terms == group_load(g))

    keep_c = 1 - net.charge_pct / 100
    m.inv = pyo.Var([(bk, s) for bk in net.buckets for s in range(net.steps)], within=pyo.NonNegativeReals)
    periods = sorted(set(net.period_of_step))
    m.lapse = pyo.Var([(bk, q) for bk in net.buckets for q in periods], within=pyo.NonNegativeReals)
    m.carry_z = pyo.Var(periods, within=pyo.Binary)
    by_step_dep: dict[tuple[str, int], list[Any]] = defaultdict(list)
    by_step_w: dict[tuple[str, int], list[Any]] = defaultdict(list)
    for k, g in bankable:
        dbk = net.deposit_bucket[g]
        assert dbk is not None
        by_step_dep[(dbk, net.group_step[g])].append(m.dep[k, g])
    for bk, g in draw_idx:
        by_step_w[(bk, net.group_step[g])].append(m.w[bk, g])
    if net.buckets:
        for s in range(net.steps):
            q = net.period_of_step[s]
            for bk in net.buckets:
                prev_inv: Any = p.start.bank_kwh.get(bk, 0.0) if p.start else 0.0
                if s > 0:
                    prev_inv = m.inv[bk, s - 1]
                    if (s - 1) in net.step_period_end:
                        prev_inv = prev_inv - m.lapse[bk, net.period_of_step[s - 1]]
                add(m.inv[bk, s] == prev_inv + keep_c * sum(by_step_dep[(bk, s)]) - sum(by_step_w[(bk, s)]))
            if s not in net.step_period_end:
                continue
            _pe, fe = net.step_period_end[s]
            for bk in net.buckets:
                add(m.lapse[bk, q] <= m.inv[bk, s])
            if fe or not net.carry:
                for bk in net.buckets:
                    add(m.lapse[bk, q] == m.inv[bk, s])
                continue
            steps_q = {x for x in range(net.steps) if net.period_of_step[x] == q}
            gq = [g for g in G if net.group_step[g] in steps_q]
            gqs = set(gq)
            ceil: list[Any] = []
            if net.cap.get("pct_of_injection") not in (None, ""):
                inj = sum(m.dep[k, g] for k, g in bankable if g in gqs)
                ceil.append(float(net.cap["pct_of_injection"]) / 100 * inj)
            if net.cap.get("pct_of_consumption") not in (None, ""):
                ceil.append(float(net.cap["pct_of_consumption"]) / 100 * sum(m.grid[g] for g in gq))
            total = sum(m.inv[bk, s] - m.lapse[bk, q] for bk in net.buckets)
            if len(ceil) == 1:
                add(total <= ceil[0], "carry_cap")
            elif len(ceil) == 2:
                if net.cap.get("combine") == "lower" or mode == "size":
                    add(total <= ceil[0], "carry_cap")
                    add(total <= ceil[1], "carry_cap")
                else:
                    big = _big_m(p, gq, net)
                    add(total <= ceil[0] + big * m.carry_z[q], "carry_cap")
                    add(total <= ceil[1] + big * (1 - m.carry_z[q]), "carry_cap")
    m.bankable = bankable
    m.periods = periods
    lapse_all = [m.lapse[bk, q] for bk in net.buckets for q in periods]

    if mode == "settle":
        obj: Any = 0
        obj -= 1000.0 * sum(m.so[k, g] for k in ks for g in G if has_supply[k][g])
        n_groups = max(1, len(net.groups))
        for bk, g in draw_idx:
            rank = net.drawable[g].index(bk)
            obj -= (10.0 * (1 - g / n_groups) + 1e-6 * (len(net.drawable[g]) - rank)) * m.w[bk, g]
        obj += 100.0 * sum(m.unb[k, g] for k in ks for g in G if has_supply[k][g] and (k, g) in dep_set)
        # keep as much as the ceiling allows at each period end (earlier lapse weighs more)
        n_q = len(periods)
        obj += sum((1.0 + n_q - i) * m.lapse[bk, q] for i, q in enumerate(periods) for bk in net.buckets)
        return obj

    cost: Any = 0
    for g, idx in enumerate(net.groups):
        cost += _group_rate(p, idx) * m.grid[g]
    if net.charge_inr:
        cost += net.charge_inr * sum(m.dep[k, g] for k, g in bankable)
    if p.lapse_inr_per_kwh and lapse_all:
        cost -= p.lapse_inr_per_kwh * sum(lapse_all)
    guard = _deposit_guard(p, net)
    cost += sum(guard[g] * m.dep[k, g] for k, g in bankable if guard[g] > 0)
    return cost


def _may_bank(p: Problem, k: str) -> bool:
    return any(c.id == k and c.may_bank for c in p.candidates)


def _deposit_guard(p: Problem, net: Netting) -> list[float]:
    """Per netting unit: what banking a kWh there could earn over setting it off in that unit —
    the best rate it could be withdrawn at in the same banking period, after the charge in kind,
    less the unit's own rate (never below zero), plus a paisa. Charged on deposits in the sizing
    model so the solver gains nothing by banking energy the rule sets off first."""
    keep = 1 - net.charge_pct / 100
    rates = [_group_rate(p, idx) for idx in net.groups]
    best: dict[tuple[int, str], float] = {}
    for g in range(len(net.groups)):
        q = net.period_of_step[net.group_step[g]]
        for bk in net.drawable[g]:
            best[(q, bk)] = max(best.get((q, bk), 0.0), rates[g])
    out = []
    for g in range(len(net.groups)):
        dbk = net.deposit_bucket[g]
        if dbk is None:
            out.append(0.0)
            continue
        q = net.period_of_step[net.group_step[g]]
        gain = keep * max(best.get((q, dbk), 0.0), best.get((q + 1, dbk), 0.0) if net.carry else 0.0)
        out.append(max(0.0, gain - rates[g]) + 0.01)
    return out


def build_settlement(p: Problem, metered: list[float], supply: dict[str, list[float]]) -> pyo.ConcreteModel:
    """The settlement pass: the solver's own settlement of a fixed dispatch under the rule's order."""
    net = netting(p)
    m = pyo.ConcreteModel(name="ergplan-settle")
    m.netting = net
    m.problem = p
    m.cons = pyo.ConstraintList()
    names: dict[int, str] = {}

    def add(expr: Any, name: str | None = None) -> None:
        if isinstance(expr, bool):
            if not expr:
                raise ValueError(f"infeasible constant constraint {name or ''}")
            return
        m.cons.add(expr)
        if name:
            names[len(m.cons)] = name

    sums = {k: [sum(v[t] for t in idx) for idx in net.groups] for k, v in supply.items()}
    obj = _settlement(
        m,
        p,
        net,
        add,
        lambda g: sum(metered[t] for t in net.groups[g]),
        lambda k, g: sums[k][g],
        {k: [x > 0 for x in v] for k, v in sums.items()},
        "settle",
    )
    m.obj = pyo.Objective(expr=obj, sense=pyo.minimize)
    m.cons_names = names
    return m


def _shape(cands: list[Candidate], cid: str) -> list[float]:
    return next(c.shape for c in cands if c.id == cid)


def _group_rate(p: Problem, idx: list[int]) -> float:
    """Grid rate of a netting unit: the block's rate, or the load-weighted mean over an aggregated
    unit (exact for ToD-slot netting, where every block of the unit has the same rate)."""
    if len(idx) == 1:
        return p.grid.rate[idx[0]]
    w = sum(p.load_kwh[t] for t in idx)
    if w <= 0:
        return sum(p.grid.rate[t] for t in idx) / len(idx)
    return sum(p.grid.rate[t] * p.load_kwh[t] for t in idx) / w


def _big_m(p: Problem, gq: list[int], net: Netting) -> float:
    if p.big_m_kwh is not None:
        return p.big_m_kwh
    blocks = [t for g in gq for t in net.groups[g]]
    supply = sum(c.max_kw * sum(c.shape[t] for t in blocks) for c in p.candidates if not c.btm)
    return max(1.0, supply + sum(p.load_kwh[t] for t in blocks))


# ---------------------------------------------------------------- resolution and chunks


def coarsen(p: Problem, factor: int) -> Problem:
    """The same year in blocks `factor` times longer (15-minute → hourly for sizing): energies summed,
    rates energy-weighted, each block taking its first quarter's slot."""
    if factor == 1:
        return p
    n = p.n
    groups = [list(range(i, min(n, i + factor))) for i in range(0, n, factor)]

    def wmean(vals: list[float], w: list[float], idx: list[int]) -> float:
        tw = sum(w[t] for t in idx)
        if tw <= 0:
            return sum(vals[t] for t in idx) / len(idx)
        return sum(vals[t] * w[t] for t in idx) / tw

    cands = []
    for c in p.candidates:
        shape = [sum(c.shape[t] for t in g) for g in groups]
        cost = [wmean(c.energy_inr_per_kwh, c.shape if any(c.shape) else [1.0] * n, g) for g in groups]
        cands.append(Candidate(**{**c.__dict__, "shape": shape, "energy_inr_per_kwh": cost}))
    grid = Grid(**{**p.grid.__dict__, "rate": [wmean(p.grid.rate, p.load_kwh, g) for g in groups]})
    return Problem(
        blocks=[p.blocks[g[0]] for g in groups],
        hours=p.hours * factor,
        load_kwh=[sum(p.load_kwh[t] for t in g) for g in groups],
        grid=grid,
        candidates=cands,
        batteries=p.batteries,
        thermals=[
            Thermal(
                **{
                    **u.__dict__,
                    "min_up_blocks": max(1, u.min_up_blocks // factor),
                    "min_down_blocks": max(1, u.min_down_blocks // factor),
                }
            )
            for u in p.thermals
        ],
        rule=p.rule,
        limits=p.limits,
        lapse_inr_per_kwh=p.lapse_inr_per_kwh,
        big_m_kwh=p.big_m_kwh,
    )


def chunk(p: Problem, idx: list[int], start: Start | None, fixed: Fixed | None) -> Problem:
    """Blocks `idx` (consecutive) of a year as a problem of their own, with the state carried in."""
    last = idx[-1]
    nxt = p.blocks[last + 1].month if last + 1 < p.n else None
    return Problem(
        blocks=[p.blocks[t] for t in idx],
        hours=p.hours,
        load_kwh=[p.load_kwh[t] for t in idx],
        grid=Grid(**{**p.grid.__dict__, "rate": [p.grid.rate[t] for t in idx]}),
        candidates=[
            Candidate(
                **{
                    **c.__dict__,
                    "shape": [c.shape[t] for t in idx],
                    "energy_inr_per_kwh": [c.energy_inr_per_kwh[t] for t in idx],
                }
            )
            for c in p.candidates
        ],
        batteries=p.batteries,
        thermals=p.thermals,
        rule=p.rule,
        limits=p.limits,
        lapse_inr_per_kwh=p.lapse_inr_per_kwh,
        big_m_kwh=p.big_m_kwh,
        next_month=nxt,
        start=start or Start(),
        fixed=fixed,
    )


def months_of(p: Problem) -> list[list[int]]:
    out: dict[date, list[int]] = {}
    for t, b in enumerate(p.blocks):
        out.setdefault(b.month, []).append(t)
    return [out[k] for k in sorted(out)]


def periods_of(p: Problem) -> list[list[int]]:
    """Consecutive blocks of each banking period of the rule (the whole year without banking)."""
    body = p.rule.body if p.rule else {}
    banking = body.get("banking") or {}
    if not banking.get("allowed"):
        return months_of(p)
    kind = str(banking.get("period", "monthly"))
    out: dict[int, list[int]] = {}
    for t, b in enumerate(p.blocks):
        out.setdefault(_period_index(b.month, kind), []).append(t)
    return [out[k] for k in sorted(out)]
