"""Runs (Stage 6): assemble the optimizer's problem for a scenario from approved rules, the load
profile and the price vintages; solve; re-settle (invariant 6); store the result with every pin
(invariant 5); replay a run from its pins. The arithmetic is in optimizer/ and settlement/ (pure);
this module reads and writes the database."""

from __future__ import annotations

import hashlib
import json
import math
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..core.sourced import RefKind, SourcedValue, SourceRef, derive
from ..core.units import Unit
from ..db.base import session_scope
from ..db.models import (
    Asset,
    Connection,
    LoadProfile,
    PricePoint,
    PriceVintage,
    Run,
    RunResult,
    Scenario,
    Site,
)
from ..engine import avoided_cost, landed_cost, lcoe, tariff_eval
from ..engine import scope as escope
from ..engine.tariff_eval import slot_adjustment_pct, slot_of
from ..intake import generation, profile_synthesis
from ..optimizer import model as om
from ..optimizer.highs_solve import Solution, SolveFailed, solve
from ..optimizer.resettle import INR, Resettled, resettle, status_quo
from ..optimizer.scenarios import CandidateSpec, ScenarioSpec, irr, payback_years, reprice
from ..rulebook.models import RuleView
from ..rulebook.repository import Reader
from ..rulebook.scope import matches
from ..rulebook.service import jurisdiction_chain
from .routers.cost import _facts, _kvah_factor, _rules_for
from .routers.landed import DEFAULT_PRICE

WORKER = "worker@ergplan"
CATEGORY = {
    "captive": "captive_generation",
    "group_captive": "captive_generation",
    "third_party": "bilateral",
}
GRID_FACTOR = (
    "0.71",
    "CEA CO2 Baseline Database, weighted average emission rate of the all-India grid (recent versions "
    "0.71–0.73 tCO2/MWh); state the version you report against",
)
ROOF_SQM_PER_KWP = Decimal(10)
ZERO = Decimal(0)


class RunError(RuntimeError):
    pass


@dataclass
class CandMeta:
    spec: CandidateSpec
    cid: str
    label: str
    price: SourcedValue | None = None
    delivered: SourcedValue | None = None
    cuf: SourcedValue | None = None
    waterfalls: dict[str, list[SourcedValue]] = field(default_factory=dict)  # slot → lines (as-of month)
    totals: list[SourcedValue] = field(default_factory=list)  # every landed total used
    capex_inr: Decimal = ZERO  # per kW (rooftop) or per kWh (battery)
    crf: SourcedValue | None = None
    life_years: int = 25
    inputs: list[SourcedValue] = field(default_factory=list)
    rule: RuleView | None = None
    gaps: list[str] = field(default_factory=list)


@dataclass
class Assembled:
    problem: om.Problem
    cands: list[CandMeta]
    rate_cards: list[SourcedValue]
    demand_inputs: list[SourcedValue]
    profile_ref: SourcedValue
    profile: LoadProfile
    vintages: list[str]
    limits: dict[str, tuple[str, list[SourcedValue]]]  # binding name → plain words, refs
    rule: RuleView | None
    notes: list[str]
    as_of: date
    cd: SourcedValue | None
    grid_factor: SourcedValue


def _f(x: Decimal | float) -> float:
    return float(x)


def _sv(value: Decimal, unit: Unit, ref: SourceRef, label: str) -> SourcedValue:
    return SourcedValue(value=value, unit=unit, source_refs=(ref,), label=label)


def _iex_prices(
    s: Session,
    segment: str,
    vintage_id: str | None,
    months: list[int],
    slots_of: dict[int, list[str]],
    tod_for: Any,
) -> tuple[dict[tuple[int, str], SourcedValue], str] | None:
    """Mean clearing price per (month, ToD slot) from a vintage (the latest live one unless pinned)."""
    q = select(PriceVintage).where(PriceVintage.segment == segment)
    q = (
        q.where(PriceVintage.id == vintage_id)
        if vintage_id
        else q.where(PriceVintage.superseded_by.is_(None))
    )
    v = s.scalars(q.order_by(PriceVintage.date_to.desc())).first()
    if v is None:
        return None
    rows = s.execute(
        select(func.extract("month", PricePoint.day), PricePoint.block, func.avg(PricePoint.mcp_inr_per_mwh))
        .where(PricePoint.vintage_id == v.id)
        .group_by(func.extract("month", PricePoint.day), PricePoint.block)
    ).all()
    by: dict[int, dict[int, Decimal]] = defaultdict(dict)
    for mo, blk, p in rows:
        by[int(mo)][int(blk)] = Decimal(str(p))
    out: dict[tuple[int, str], SourcedValue] = {}
    for mo in months:
        tod = tod_for(mo)
        for name in slots_of[mo]:
            blocks = [
                b
                for b in by.get(mo, {})
                if tod is None or (slot_of(tod, mo, (b - 1) * 15) or {}).get("name") == name
            ]
            if not blocks:
                continue
            mean = sum((by[mo][b] for b in blocks), ZERO) / len(blocks) / 1000
            out[(mo, name)] = _sv(
                mean.quantize(Decimal("0.0001")),
                Unit.INR_PER_KWH,
                SourceRef(
                    kind=RefKind.MARKET,
                    vintage_id=v.id,
                    note=f"mean clearing price, {name}, month {mo}, {v.filename} "
                    f"({v.date_from} to {v.date_to})",
                ),
                f"IEX {segment.upper()} MCP",
            )
    return out, v.id


def assemble(
    s: Session,
    sc: Scenario,
    spec: ScenarioSpec,
    reader: Reader,
    profile_id: str | None = None,
    vintage_pins: dict[str, str] | None = None,
) -> Assembled:
    conn = s.get(Connection, sc.connection_id)
    if conn is None:
        raise RunError("connection not found")
    site = s.get(Site, conn.site_id)
    assert site is not None
    q = select(LoadProfile).where(LoadProfile.connection_id == conn.id)
    q = q.where(LoadProfile.id == profile_id) if profile_id else q.order_by(LoadProfile.version.desc())
    lp = s.scalars(q).first()
    if lp is None:
        raise RunError("no load profile for this connection")
    as_of = spec.as_of or date.today()
    kw = profile_synthesis.decode(lp.series_kw)
    days = profile_synthesis.year_days(lp.year_start)
    facts = _facts(s, conn)
    chain = jurisdiction_chain(s, facts.discom)
    rules_for = _rules_for(s, facts, as_of, reader)
    factor, pf = _kvah_factor(s, conn)
    notes: list[str] = []

    # blocks, ToD slots and the avoided-cost rate of each block
    month_firsts = sorted({date(d.year, d.month, 1) for d in days})
    card_rate: dict[tuple[date, str], SourcedValue] = {}
    slot_meta: dict[date, list[tuple[int | None, str, frozenset[str]]]] = {}
    slots_of: dict[int, list[str]] = {}
    for mf in month_firsts:
        mr = rules_for(mf)
        if mr.schedule is None:
            raise RunError(f"no approved tariff schedule for {mf:%b %Y}")
        names = []
        if mr.tod is not None:
            for i, sl in enumerate(mr.tod.body.get("slots", [])):
                if sl.get("months") and mf.month not in sl["months"]:
                    continue
                card = avoided_cost.rate_card(mf, mr, i, factor, conn.contract_demand_kva)
                if card is not None:
                    card_rate[(mf, str(sl["name"]))] = card.rate_inr_per_kwh
                names.append(str(sl["name"]))
        if not names:
            card = avoided_cost.rate_card(mf, mr, None, factor, conn.contract_demand_kva)
            assert card is not None
            card_rate[(mf, "all hours")] = card.rate_inr_per_kwh
            names = ["all hours"]
        slots_of[mf.month] = names
        slot_meta[mf] = []
    hours = spec.resolution_min / 60
    step = spec.resolution_min // 15
    blocks: list[om.BlockMeta] = []
    load: list[float] = []
    rate: list[float] = []
    load_d: list[Decimal] = []
    rate_d: list[Decimal] = []
    for i in range(0, len(kw), step):
        day = days[i // 96]
        mf = date(day.year, day.month, 1)
        tod = rules_for(mf).tod
        sl = slot_of(tod, day.month, (i % 96) * 15) if tod else None
        name = str(sl["name"]) if sl else "all hours"
        cls = frozenset({"peak" if sl and slot_adjustment_pct(sl) > 0 else "off_peak"})
        blocks.append(om.BlockMeta(mf, name, cls, i // 4))
        load_d.append(sum(kw[i : i + step], ZERO) * Decimal("0.25"))
        load.append(_f(load_d[-1]))
        rv = card_rate.get((mf, name))
        if rv is None:
            raise RunError(f"no avoided-cost rate for {name} in {mf:%b %Y}")
        rate.append(_f(rv.value))
        rate_d.append(rv.value)

    # demand side
    demand_rate: dict[date, float] = {}
    excess_rate: dict[date, float] = {}
    demand_d: dict[date, Decimal] = {}
    excess_d: dict[date, Decimal] = {}
    floor = ZERO
    demand_inputs: list[SourcedValue] = []
    slabs_d: dict[date, list[tuple[Decimal | None, Decimal]]] = {}
    excess_abs_d: dict[date, Decimal] = {}
    min_kva = ZERO
    cd_level = conn.contract_demand_kva or ZERO
    for mf in month_firsts:
        sch = rules_for(mf).schedule
        assert sch is not None
        dc = sch.get("/demand_charge/value")
        if dc not in (None, ""):
            slabs = tariff_eval.demand_slabs(sch)
            # the solver sees the slab rate at contract demand; the judge prices every slab exactly
            marginal = tariff_eval.marginal_demand_rate(sch, cd_level) or Decimal(str(dc))
            demand_d[mf] = marginal
            demand_rate[mf] = _f(marginal)
            for _, rate_v, ptr in slabs:
                sv = _sv(rate_v, Unit.INR_PER_KVA_MONTH, sch.ref(ptr), "Demand charge")
                if sv not in demand_inputs:
                    demand_inputs.append(sv)
            if len(slabs) > 1:
                slabs_d[mf] = [(hi, rate_v) for hi, rate_v, _ in slabs]
            ex_abs = sch.get("/demand_charge/billing_demand_rule/excess_demand_rate")
            mult = sch.get("/demand_charge/billing_demand_rule/excess_demand_penalty_multiplier")
            if ex_abs not in (None, ""):
                excess_abs_d[mf] = Decimal(str(ex_abs))
                slabs_d.setdefault(mf, [(hi, rate_v) for hi, rate_v, _ in slabs])
                excess_d[mf] = max(Decimal(str(ex_abs)) - marginal, ZERO)  # on top of the marginal rate
                excess_rate[mf] = _f(excess_d[mf])
            elif mult not in (None, ""):
                excess_d[mf] = Decimal(str(dc)) * Decimal(str(mult))
                excess_rate[mf] = _f(excess_d[mf])
        mk = sch.get("/demand_charge/billing_demand_rule/min_kva")
        if mk not in (None, ""):
            min_kva = Decimal(str(mk))
        fp = sch.get("/demand_charge/billing_demand_rule/min_pct_of_contract_demand")
        if fp not in (None, ""):
            floor = Decimal(str(fp))
    cd_kva = conn.contract_demand_kva or ZERO
    cd_sv = (
        _sv(
            cd_kva, Unit.KVA, SourceRef(kind=RefKind.CLIENT_STATED, note="contract demand"), "Contract demand"
        )
        if conn.contract_demand_kva
        else None
    )
    cds = spec.contract_demand
    grid = om.Grid(
        rate=rate,
        demand_rate=demand_rate,
        floor_pct=_f(floor),
        excess_rate=excess_rate,
        cd_kva=_f(cd_kva),
        pf=_f(pf.value),
        cd_step_kva=_f(cds.step_kva) if cds else None,
        cd_min_kva=_f(cds.min_kva or ZERO) if cds else 0.0,
        cd_max_kva=_f(cds.max_kva or cd_kva) if cds else None,
        cd_change_inr_per_kva_year=_f(cds.change_inr_per_kva_year) if cds else 0.0,
    )

    # rules for open access
    oa_rows = reader(s, "oa_charge", chain, as_of)
    waivers = reader(s, "ists_waiver", chain, as_of)
    settlements = reader(s, "settlement", chain, as_of)
    limit_rows = reader(s, "regulatory_limit", chain, as_of)
    ctx0 = escope.context(facts, date(as_of.year, as_of.month, 1))
    limits: list[om.Limit] = []
    limit_words: dict[str, tuple[str, list[SourcedValue]]] = {}
    min_oa_kw: tuple[float, SourcedValue] | None = None
    for r in limit_rows:
        if not matches(r.scope, ctx0):
            continue
        kind = str(r.body["limit"])
        v = Decimal(str(r.body["value"]))
        sv = _sv(
            v, Unit.PERCENT if r.body["unit"] == "percent" else Unit.COUNT, r.ref("/value"), r.label or kind
        )
        if kind == "min_oa_capacity_mw":
            min_oa_kw = (_f(v * 1000), sv)
            continue
        limits.append(om.Limit(kind, _f(v), r.label or kind, {}, None))
        limit_words[f"limit:{kind}:"] = (_limit_words(kind, v, r), [sv])

    cands: list[CandMeta] = []
    problem_cands: list[om.Candidate] = []
    batteries: list[om.Battery] = []
    vintages: list[str] = []
    governing: RuleView | None = None
    n = len(blocks)
    months = sorted(slots_of)
    first_of = {mf.month: mf for mf in month_firsts}

    energy_d: dict[str, list[Decimal]] = {}
    fixed_kw: dict[str, Decimal] = {}
    fixed_kwh: dict[str, Decimal] = {}

    def per_block(cid: str, by_slot: dict[tuple[int, str], Decimal]) -> list[float]:
        energy_d[cid] = [by_slot.get((b.month.month, b.slot), ZERO) for b in blocks]
        return [_f(x) for x in energy_d[cid]]

    for idx, cs in enumerate(spec.candidates):
        src = landed_cost.SOURCE_BY_ID[cs.kind]
        cid = f"{cs.kind}_{idx}" if sum(1 for x in spec.candidates if x.kind == cs.kind) > 1 else cs.kind
        meta = CandMeta(spec=cs, cid=cid, label=src.label)
        ownership = cs.ownership or ("group_captive" if cs.kind == "group_captive" else "third_party")
        if cs.kind == "btm_bess":
            st = lcoe.default_bess()
            f = lcoe.crf(st.discount_pct, st.life_years)
            yearly = st.capex_inr_per_kwh.value * (f.value + st.om_pct_of_capex.value / 100)
            rt = math.sqrt(_f(st.round_trip_pct.value) / 100)
            mx = cs.max_mw * 1000 if cs.max_mw else cd_kva * Decimal("0.5")
            batteries.append(
                om.Battery(
                    cid,
                    max_kw=_f(mx),
                    min_kw=_f(cs.min_mw * 1000),
                    eff_charge=rt,
                    eff_discharge=rt,
                    inr_per_kwh_year=_f(yearly),
                )
            )
            meta.capex_inr, meta.crf, meta.life_years = (
                st.capex_inr_per_kwh.value,
                f,
                int(st.life_years.value),
            )
            fixed_kwh[cid] = yearly
            meta.inputs = [st.capex_inr_per_kwh, st.om_pct_of_capex, st.round_trip_pct, f]
            if not cs.max_mw:
                notes.append(
                    f"{cid}: at most half the contract demand in kW (assumption; set a limit to change it)"
                )
            cands.append(meta)
            continue
        if cs.kind == "rooftop_pv":
            g = lcoe.default_rooftop()
            f = lcoe.crf(g.discount_pct, g.life_years)
            yearly = g.capex_inr_per_kw.value * (f.value + g.om_pct_of_capex.value / 100)
            raw, cuf = generation.profile(
                generation.curve_for("solar", site.state), Decimal(1), lp.year_start
            )
            scale = g.cuf_pct.value / cuf
            shape = _resample([v * scale * Decimal("0.25") for v in raw], step)
            if site.roof_sqm:
                mx = site.roof_sqm / ROOF_SQM_PER_KWP
                roof = _sv(
                    site.roof_sqm,
                    Unit.COUNT,
                    SourceRef(kind=RefKind.CLIENT_STATED, note="roof area, m²"),
                    "Roof area",
                )
                per = _sv(
                    ROOF_SQM_PER_KWP,
                    Unit.COUNT,
                    SourceRef(kind=RefKind.ASSUMPTION, note="10 m² of roof per kWp"),
                    "Roof per kWp",
                )
                limits.append(om.Limit("max_rooftop_kw", _f(mx), "roof area", {}, cid))
                limit_words[f"limit:max_rooftop_kw:{cid}"] = (
                    f"Rooftop solar limited by the roof: {site.roof_sqm} m² at 10 m² per kWp",
                    [roof, per],
                )
            mx2 = (
                cs.max_mw * 1000
                if cs.max_mw
                else (site.roof_sqm / ROOF_SQM_PER_KWP if site.roof_sqm else cd_kva)
            )
            problem_cands.append(
                om.Candidate(
                    cid,
                    shape=shape,
                    energy_inr_per_kwh=[0.0] * n,
                    fixed_inr_per_kw_year=_f(yearly),
                    min_kw=_f(cs.min_mw * 1000),
                    max_kw=_f(mx2),
                    btm=True,
                )
            )
            meta.capex_inr, meta.crf, meta.life_years = g.capex_inr_per_kw.value, f, int(g.life_years.value)
            meta.cuf = g.cuf_pct
            fixed_kw[cid] = yearly
            energy_d[cid] = [ZERO] * n
            meta.inputs = [g.capex_inr_per_kw, g.om_pct_of_capex, g.cuf_pct, f]
            cands.append(meta)
            continue
        # open access (PPA or exchange)
        src_ctx = {**ctx0, "connection": src.connection, "source": src.source, "ownership": ownership}
        own_rule = next((r for r in settlements if matches(r.scope, src_ctx)), None)
        if governing is None and own_rule is not None:
            governing = own_rule
        meta.rule = own_rule
        if own_rule is None:
            # no approved settlement rule for this ownership in the state: the simulator sets off
            # in the same block with no banking, which the plan must say (rule 13)
            meta.gaps.append("settlement_rule")
        if src.price_kind == "iex":
            got = _iex_prices(
                s,
                src.iex_segment or "",
                (vintage_pins or {}).get(src.iex_segment or ""),
                months,
                slots_of,
                lambda mo: rules_for(first_of[mo]).tod,
            )
            if got is None:
                raise RunError(f"no {str(src.iex_segment).upper()} prices loaded")
            prices, vid = got
            vintages.append(vid)
            oa_shape: list[float] | None = [hours * 1.0] * n
            mx = cs.max_mw * 1000 if cs.max_mw else cd_kva
            cuf_sv = None
        else:
            if cs.price_inr_per_kwh is not None:
                p = _sv(
                    cs.price_inr_per_kwh,
                    Unit.INR_PER_KWH,
                    SourceRef(kind=RefKind.CLIENT_STATED),
                    "PPA tariff",
                )
            else:
                val, note = DEFAULT_PRICE[cs.kind]
                p = _sv(
                    Decimal(val),
                    Unit.INR_PER_KWH,
                    SourceRef(kind=RefKind.ASSUMPTION, note=f"{note}; change it to your quote"),
                    "PPA tariff",
                )
            meta.price = p
            prices = {(mo, nm): p for mo in months for nm in slots_of[mo]}
            raw, cuf = generation.profile(
                generation.curve_for(src.source, site.state), Decimal(1), lp.year_start
            )
            cuf_sv = _sv(
                cuf,
                Unit.PERCENT,
                SourceRef(
                    kind=RefKind.ASSUMPTION,
                    note=f"normative {src.source} curve for {site.state} (packages/profiles/cuf)",
                ),
                "CUF",
            )
            meta.cuf = cuf_sv
            mx = cs.max_mw * 1000 if cs.max_mw else cd_kva * 3
            oa_shape = None  # after the delivered share is known
        energy: dict[tuple[int, str], Decimal] = {}
        delivered = None
        for mo in months:
            mdate = date(as_of.year if mo >= as_of.month else as_of.year + 1, mo, 15)
            ctx = escope.context(facts, mdate)
            for nm in slots_of[mo]:
                pr = prices.get((mo, nm))
                if pr is None:
                    continue
                wf = landed_cost.evaluate(
                    src,
                    ctx,
                    landed_cost.Scenario(
                        price=pr,
                        ownership=ownership,
                        commissioned=cs.commissioned,
                        on=as_of,
                        capacity_mw=_sv(
                            Decimal(1),
                            Unit.MW,
                            SourceRef(
                                kind=RefKind.ASSUMPTION,
                                note="per MW, for capacity charges over scheduled energy",
                            ),
                            "Capacity",
                        ),
                        cuf_pct=cuf_sv,
                    ),
                    oa_rows,
                    waivers,
                    None,  # banking is settled by the model and the judge, not as an upper bound
                )
                energy[(mo, nm)] = wf.total.value
                meta.totals.append(wf.total)
                meta.gaps += wf.gaps
                delivered = delivered or wf.delivered
                if mo == as_of.month:
                    meta.waterfalls[nm] = wf.lines
        meta.delivered = delivered
        keep = delivered.value if delivered else Decimal(1)
        if oa_shape is None:
            oa_shape = _resample([v * keep * Decimal("0.25") for v in raw], step)
        problem_cands.append(
            om.Candidate(
                cid,
                shape=oa_shape,
                energy_inr_per_kwh=per_block(cid, energy),
                min_kw=_f(cs.min_mw * 1000),
                max_kw=_f(mx),
                category="exchange" if src.price_kind == "iex" else CATEGORY[ownership],
                may_bank=False,  # set below once the governing rule is known
                renewable=src.price_kind != "iex",
                min_size_kw=min_oa_kw[0] if min_oa_kw and src.price_kind != "iex" else 0.0,
                dispatchable=src.price_kind == "iex",
            )
        )
        if min_oa_kw and src.price_kind != "iex":
            limit_words[f"min_size:{cid}"] = (
                f"Open access needs at least {Decimal(str(min_oa_kw[0])) / 1000} MW per source",
                [min_oa_kw[1]],
            )
        meta.inputs = [x for x in (meta.price, delivered, cuf_sv) if x is not None]
        meta.gaps = list(dict.fromkeys(meta.gaps))
        cands.append(meta)
    # who may bank: the sources the governing rule's scope covers
    final: list[om.Candidate] = []
    for c in problem_cands:
        m = next(x for x in cands if x.cid == c.id)
        may = governing is not None and m.rule is not None and m.rule.id == governing.id
        final.append(om.Candidate(**{**c.__dict__, "may_bank": may}))
    for m in cands:
        if m.spec.max_mw:
            limit_words[f"max_kw:{m.cid}"] = (
                f"{m.label}: the most you allowed ({m.spec.max_mw} MW)",
                [_sv(m.spec.max_mw, Unit.MW, SourceRef(kind=RefKind.CLIENT_STATED), "Maximum")],
            )
        else:
            limit_words[f"max_kw:{m.cid}"] = (
                f"{m.label}: the default upper bound (assumption; set a maximum to change it)",
                [_sv(ZERO, Unit.MW, SourceRef(kind=RefKind.ASSUMPTION, note="default bound"), "Maximum")],
            )
    if governing is not None and "carry_cap" not in limit_words:
        limit_words["carry_cap"] = (
            "Banked energy carried to the next month is capped by the settlement rule",
            [_sv(ZERO, Unit.COUNT, governing.ref("/banking/cap"), "Carry-over ceiling")]
            if governing.get("/banking/cap") is not None
            else [],
        )
    if cd_sv is not None and floor:
        sch = rules_for(month_firsts[0]).schedule
        assert sch is not None
        limit_words["cd_floor"] = (
            f"Billing demand is at least {floor}% of contract demand, "
            "so lowering peaks below that saves nothing",
            [
                cd_sv,
                _sv(
                    floor,
                    Unit.PERCENT,
                    sch.ref("/demand_charge/billing_demand_rule/min_pct_of_contract_demand"),
                    "Floor",
                ),
            ],
        )
    thermals = _thermals(s, site.id, hours, notes)
    lapse = spec.lapse_price_inr_per_kwh or ZERO
    problem = om.Problem(
        blocks=blocks,
        hours=hours,
        load_kwh=load,
        grid=grid,
        candidates=final,
        batteries=batteries,
        thermals=thermals,
        rule=governing,
        limits=limits,
        lapse_inr_per_kwh=_f(lapse),
        exact=om.Exact(
            load_kwh=load_d,
            rate=rate_d,
            demand_rate=demand_d,
            excess_rate=excess_d,
            floor_pct=floor,
            cd_kva=cd_kva,
            pf=pf.value,
            energy=energy_d,
            fixed_kw=fixed_kw,
            fixed_kwh=fixed_kwh,
            fuel={u.id: Decimal(repr(u.fuel_inr_per_kwh)) for u in thermals},
            lapse=lapse,
            cd_change=cds.change_inr_per_kva_year if cds else ZERO,
            demand_slabs=slabs_d,
            excess_abs=excess_abs_d,
            min_kva=min_kva,
        ),
    )
    profile_ref = _sv(
        sum(kw, ZERO) * Decimal("0.25"),
        Unit.KWH,
        SourceRef(
            kind=RefKind.MEASURED if lp.provenance == "measured" else RefKind.DERIVED,
            note=f"load profile v{lp.version} ({lp.provenance}), year from {lp.year_start}",
        ),
        "Load profile energy",
    )
    gf = (
        _sv(
            spec.grid_factor_t_per_mwh,
            Unit.TCO2_PER_MWH,
            SourceRef(kind=RefKind.CLIENT_STATED),
            "Grid emission factor",
        )
        if spec.grid_factor_t_per_mwh
        else _sv(
            Decimal(GRID_FACTOR[0]),
            Unit.TCO2_PER_MWH,
            SourceRef(kind=RefKind.ASSUMPTION, note=GRID_FACTOR[1]),
            "Grid emission factor",
        )
    )
    return Assembled(
        problem=problem,
        cands=cands,
        rate_cards=list(dict.fromkeys(card_rate.values())),
        demand_inputs=demand_inputs,
        profile_ref=profile_ref,
        profile=lp,
        vintages=vintages,
        limits=limit_words,
        rule=governing,
        notes=notes,
        as_of=as_of,
        cd=cd_sv,
        grid_factor=gf,
    )


def _resample(q: list[Decimal], step: int) -> list[float]:
    """kWh per kW per 15-minute block → per block of `step` quarter-hours."""
    if step == 1:
        return [_f(x) for x in q]
    return [_f(sum(q[i : i + step], ZERO)) for i in range(0, len(q), step)]


def _limit_words(kind: str, v: Decimal, r: RuleView) -> str:
    words = {
        "re_cap_pct_of_contract_demand": f"Renewable capacity capped at {v}% of contract demand",
        "re_cap_pct_of_sanctioned_load": f"Renewable capacity capped at {v}% of sanctioned load",
        "storage_mandate_pct_of_re": f"Storage of at least {v}% of renewable capacity",
        "storage_mandate_pct_of_contract_demand": f"Storage of at least {v}% of contract demand",
        "min_contract_demand_for_oa_kva": f"Open access needs a contract demand of at least {v} kVA",
        "max_rooftop_kw": f"Rooftop solar at most {v} kW",
        "min_bess_hours": f"Storage of at least {v} hours",
    }
    return f"{words.get(kind, kind)} ({r.label or 'regulatory limit'})"


def _thermals(s: Session, site_id: str, hours: float, notes: list[str]) -> list[om.Thermal]:
    out = []
    for a in s.scalars(select(Asset).where(Asset.site_id == site_id, Asset.kind == "captive_thermal")):
        p = a.params or {}
        if not p.get("capacity_kw") or not p.get("variable_cost_inr_per_kwh"):
            notes.append("the captive thermal plant needs its capacity and variable cost to be dispatched")
            continue
        out.append(
            om.Thermal(
                a.id,
                capacity_kw=float(p["capacity_kw"]),
                tech_min_pct=float(p.get("tech_min_pct", 0)),
                ramp_kw_per_hour=float(p["ramp_kw_per_hour"]) if p.get("ramp_kw_per_hour") else None,
                min_up_blocks=max(1, round(float(p.get("min_up_hours", 0)) / hours)),
                min_down_blocks=max(1, round(float(p.get("min_down_hours", 0)) / hours)),
                must_run=bool(p.get("must_run")),
                fuel_inr_per_kwh=float(p["variable_cost_inr_per_kwh"]),
                start_inr=float(p.get("start_cost_inr", 0)),
            )
        )
    return out


# ---------------------------------------------------------------- results


def _q(x: Decimal, places: str = "0.001") -> Decimal:
    return x.quantize(Decimal(places))


def summarise(a: Assembled, sol: Solution, rs: Resettled) -> dict[str, Any]:
    """The client-facing result: every number a SourcedValue carrying the refs of its inputs."""
    p = a.problem
    before_lines = status_quo(p)
    after_lines = rs.costs
    grid_inputs = [*a.rate_cards, *a.demand_inputs, a.profile_ref, *([a.cd] if a.cd else [])]
    all_inputs = list(grid_inputs)
    for m in a.cands:
        all_inputs += m.inputs + m.totals
    if a.rule is not None:
        all_inputs.append(_sv(ZERO, Unit.COUNT, a.rule.ref("/granularity"), "Settlement rule"))
    before = sum(before_lines.values(), ZERO)
    after = sum(after_lines.values(), ZERO)
    saving = before - after
    capex = ZERO
    annualised = ZERO
    life = 25
    for m in a.cands:
        if m.crf is None:
            continue
        size = (
            Decimal(str(sol.bess_kwh.get(m.cid, 0.0)))
            if m.spec.kind == "btm_bess"
            else Decimal(str(sol.cap_kw.get(m.cid, 0.0)))
        )
        size = _q(size)
        capex += size * m.capex_inr
        annualised += size * m.capex_inr * m.crf.value
        life = min(life, m.life_years)
    cash = saving + annualised  # yearly cash saving: the annualised capital is paid up front instead
    # Payback and IRR only when every source sized is owned plant: with a PPA in the mix the saving is
    # mostly the PPA's, which needs no capital, and a ratio on the owned part alone would mislead.
    ppa = any(m.crf is None and Decimal(str(sol.cap_kw.get(m.cid, 0.0))) > 0 for m in a.cands)
    pay = None if ppa else payback_years(capex, cash)
    rate = irr([-capex] + [cash] * life) if capex > 0 and not ppa else None
    if ppa and capex > 0:
        a.notes.append(
            "payback and IRR are shown only when all the plant is owned; here an open-access purchase "
            "brings most of the saving without capital"
        )

    def sv(v: Decimal, unit: Unit, label: str, inputs: list[SourcedValue]) -> dict[str, Any]:
        return derive(_q(v, "0.01") if unit == Unit.INR else _q(v), unit, inputs, label=label).model_dump(
            mode="json"
        )

    sizes = []
    for m in a.cands:
        if m.spec.kind == "btm_bess":
            sizes.append(
                {
                    "id": m.cid,
                    "kind": m.spec.kind,
                    "label": m.label,
                    "kw": sv(
                        Decimal(str(sol.bess_kw[m.cid])), Unit.KW, "Battery power", [*m.inputs, *grid_inputs]
                    ),
                    "kwh": sv(
                        Decimal(str(sol.bess_kwh[m.cid])),
                        Unit.KWH,
                        "Battery energy",
                        [*m.inputs, *grid_inputs],
                    ),
                }
            )
            continue
        cap = Decimal(str(sol.cap_kw[m.cid]))
        series = sol.gen[m.cid] if m.spec.kind == "rooftop_pv" else sol.delivered[m.cid]
        delivered = sum((Decimal(f"{x:.3f}") for x in series), ZERO)
        setoff = sum(rs.result.setoff_kwh.get(m.cid, []), ZERO) if m.spec.kind != "rooftop_pv" else delivered
        ins = [*m.inputs, *m.totals, *grid_inputs]
        row: dict[str, Any] = {
            "id": m.cid,
            "kind": m.spec.kind,
            "label": m.label,
            "kw": sv(cap, Unit.KW, "Capacity", ins),
            "delivered_kwh": sv(delivered, Unit.KWH, "Energy at the meter", ins),
            "setoff_kwh": sv(setoff, Unit.KWH, "Set off against consumption", ins),
            "energy_cost": sv(
                after_lines.get(f"energy:{m.cid}", ZERO) + after_lines.get(f"fixed:{m.cid}", ZERO),
                Unit.INR,
                "Cost for the year",
                ins,
            ),
            "waterfall": {k: [x.model_dump(mode="json") for x in v] for k, v in m.waterfalls.items()},
            "gaps": m.gaps,
        }
        if m.spec.kind != "rooftop_pv":
            for key, label, src in (
                ("banked_kwh", "Banked (after the charge in kind)", rs.result.deposit_kwh),
                ("unbanked_kwh", "Surplus not banked", rs.result.unbanked_kwh),
            ):
                row[key] = sv(sum(src.get(m.cid, []), ZERO), Unit.KWH, label, ins)
        sizes.append(row)
    lapsed = sum((x["kwh"] for x in rs.result.lapsed), ZERO)
    grid_before = sum((Decimal(f"{x:.3f}") for x in p.load_kwh), ZERO)
    grid_after = sum(rs.result.grid_kwh, ZERO)
    gf = a.grid_factor
    binding = []
    for name in sol.binding:
        words, refs = a.limits.get(name, (name, []))
        binding.append({"name": name, "words": words, "refs": [r.model_dump(mode="json") for r in refs]})
    return {
        "sizes": sizes,
        "annual": {
            "before": sv(before, Unit.INR, "Grid cost today, for the year", grid_inputs),
            "after": sv(after, Unit.INR, "Cost with the plan, for the year (re-settled)", all_inputs),
            "saving": sv(saving, Unit.INR, "Saving for the year", all_inputs),
            "capex": sv(capex, Unit.INR, "Capital cost (rooftop and battery)", all_inputs),
        },
        "lines_before": {k: str(v) for k, v in before_lines.items()},
        "lines_after": {k: str(v) for k, v in after_lines.items()},
        "payback_years": sv(pay, Unit.YEARS, "Simple payback", all_inputs) if pay is not None else None,
        "irr_pct": sv(rate, Unit.PERCENT, "IRR", all_inputs) if rate is not None else None,
        "emissions": {
            "factor": gf.model_dump(mode="json"),
            "before_t": sv(
                grid_before * gf.value / 1000, Unit.TCO2, "Grid emissions today", [a.profile_ref, gf]
            ),
            "after_t": sv(
                grid_after * gf.value / 1000, Unit.TCO2, "Grid emissions with the plan", [*all_inputs, gf]
            ),
        },
        "settlement": {
            "grid_kwh": sv(grid_after, Unit.KWH, "Drawn from the DISCOM", all_inputs),
            "lapsed_kwh": sv(lapsed, Unit.KWH, "Lapsed", all_inputs),
            "withdrawn_kwh": sv(
                sum(rs.result.withdrawn_kwh, ZERO), Unit.KWH, "Withdrawn from the bank", all_inputs
            ),
            "rule": a.rule.label if a.rule else None,
        },
        "contract_demand_kva": sv(Decimal(str(sol.cd_kva)), Unit.KVA, "Contract demand", grid_inputs),
        "binding": binding,
        "provenance": {
            "load_profile": f"v{a.profile.version} ({a.profile.provenance})",
            "prices": a.vintages,
            "profile_ref": a.profile_ref.model_dump(mode="json"),
        },
        "sensitivities": [],
        "notes": a.notes,
    }


def sensitivities(spec: ScenarioSpec, summary: dict[str, Any], a: Assembled) -> list[dict[str, Any]]:
    before = Decimal(summary["annual"]["before"]["value"])
    lines = {k: Decimal(v) for k, v in summary["lines_after"].items()}
    out = []
    for snt in spec.sensitivities:
        for pct in snt.pct:
            if snt.kind == "grid_rate":
                b = before * (100 + pct) / 100
                after = reprice(lines, "grid_energy", pct)
                label = f"Grid energy rate {pct:+}%"
            else:
                cid = next((m.cid for m in a.cands if m.spec.kind == snt.candidate), None)
                if cid is None:
                    continue
                b = before
                after = reprice(lines, f"energy:{cid}", pct)
                label = f"{snt.candidate} price {pct:+}% (sizes held)"
            out.append(
                {
                    "label": label,
                    "saving": derive(
                        (b - after).quantize(INR),
                        Unit.INR,
                        [
                            _sv(
                                pct,
                                Unit.PERCENT,
                                SourceRef(kind=RefKind.CLIENT_STATED, note="sensitivity"),
                                label,
                            )
                        ],
                        label="Saving for the year",
                    ).model_dump(mode="json"),
                }
            )
    return out


def digest(summary: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(summary, sort_keys=True, default=str).encode()).hexdigest()


def dispatch_blob(a: Assembled, sol: Solution, rs: Resettled) -> bytes:
    p = a.problem
    series: dict[str, list[str]] = {
        "load": [f"{x:.3f}" for x in p.load_kwh],
        "metered": [format(b.load_kwh, "f") for b in rs.blocks],
        "grid": [format(x.quantize(Decimal("0.001")), "f") for x in rs.result.grid_kwh],
        "withdrawn": [format(x.quantize(Decimal("0.001")), "f") for x in rs.result.withdrawn_kwh],
    }
    for k, v in sol.delivered.items():
        series[f"supply:{k}"] = [f"{x:.3f}" for x in v]
    for k, v in sol.gen.items():
        series[f"supply:{k}"] = [f"{x:.3f}" for x in v]
    for k, v in sol.discharge.items():
        series[f"discharge:{k}"] = [f"{x:.3f}" for x in v]
    for k, v in sol.charge.items():
        series[f"charge:{k}"] = [f"{x:.3f}" for x in v]
    for k, v in sol.soc.items():
        series[f"soc:{k}"] = [f"{x:.3f}" for x in v]
    body = {
        "year_start": a.profile.year_start.isoformat(),
        "minutes": int(p.hours * 60),
        "slots": [b.slot for b in p.blocks],
        "series": series,
    }
    return zlib.compress(json.dumps(body).encode())


def read_dispatch(blob: bytes) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(zlib.decompress(blob))
    return out


# ---------------------------------------------------------------- execution


def create_run(s: Session, sc: Scenario, actor: str, replay_of: Run | None = None) -> Run:
    spec = ScenarioSpec.model_validate(replay_of.spec if replay_of else sc.spec)
    run = Run(
        scenario_id=sc.id,
        status="queued",
        resolution_min=spec.resolution_min,
        spec=spec.model_dump(mode="json"),
        pins=dict(replay_of.pins) if replay_of else {},
        solver={},
        created_by=actor,
        replay_of=replay_of.id if replay_of else None,
    )
    s.add(run)
    s.flush()
    return run


def execute(run_id: str) -> str:
    """Solve, re-settle and store a queued run. Returns the final status."""
    st = get_settings()
    with session_scope(actor=WORKER) as s:
        run = s.get(Run, run_id)
        if run is None:
            raise RunError("run not found")
        if run.status != "running":
            run.status = "running"
            run.started_at = datetime.now(UTC)
    try:
        with session_scope(actor=WORKER) as s:
            run = s.get(Run, run_id)
            assert run is not None
            sc = s.get(Scenario, run.scenario_id)
            assert sc is not None
            spec = ScenarioSpec.model_validate(run.spec)
            pins = run.pins or {}
            reader = Reader(pins.get("rulebook_versions") if run.replay_of else None)
            a = assemble(
                s,
                sc,
                spec,
                reader,
                profile_id=pins.get("load_profile_id") if run.replay_of else None,
                vintage_pins=pins.get("price_vintages_by_segment") if run.replay_of else None,
            )
            used_versions = sorted(reader.used)
            vint_by_seg = {
                seg: vid
                for seg, vid in s.execute(
                    select(PriceVintage.segment, PriceVintage.id).where(PriceVintage.id.in_(a.vintages))
                ).all()
            }
        sol = solve(a.problem, st.ergplan_optimizer_time_limit_s, st.ergplan_optimizer_mip_gap)
        rs = resettle(a.problem, sol, st.ergplan_resettle_tolerance_kwh)
        summary = summarise(a, sol, rs)
        summary["sensitivities"] = sensitivities(spec, summary, a)
        status = "done" if rs.agrees else "failed_resettle"
        resettle_doc = {
            "agrees": rs.agrees,
            "max_diff_kwh": str(rs.max_diff_kwh),
            "tolerance_kwh": str(st.ergplan_resettle_tolerance_kwh),
            "by_month": {
                mo.isoformat(): {q: {k: str(v) for k, v in d.items()} for q, d in row.items()}
                for mo, row in rs.by_month.items()
            },
            "solver_objective_inr": str(Decimal(f"{sol.objective:.2f}")),
            "resettled_cost_inr": str(Decimal(summary["annual"]["after"]["value"]).quantize(INR)),
        }
        with session_scope(actor=WORKER) as s:
            run = s.get(Run, run_id)
            assert run is not None
            run.pins = {
                "rulebook_versions": used_versions,
                "load_profile_id": a.profile.id,
                "load_profile_version": a.profile.version,
                "price_vintages": a.vintages,
                "price_vintages_by_segment": vint_by_seg,
                "solver": sol.solver,
                "resolution_min": run.resolution_min,
                "as_of": a.as_of.isoformat(),
            }
            run.solver = {
                "status": sol.status,
                "gap": sol.gap,
                "seconds": round(sol.seconds, 2),
                "objective_inr": f"{sol.objective:.2f}",
                "blocks": a.problem.n,
            }
            run.status = status
            run.error = None if rs.agrees else f"re-settlement differs by {rs.max_diff_kwh} kWh"
            run.finished_at = datetime.now(UTC)
            s.merge(
                RunResult(
                    run_id=run_id,
                    summary=summary,
                    resettle=resettle_doc,
                    dispatch=dispatch_blob(a, sol, rs),
                    digest=digest(summary),
                )
            )
        return status
    except (RunError, SolveFailed, ValueError) as e:
        with session_scope(actor=WORKER) as s:
            run = s.get(Run, run_id)
            assert run is not None
            run.status = "failed"
            run.error = str(e)[:2000]
            run.finished_at = datetime.now(UTC)
        return "failed"


def claim_next() -> str | None:
    """Take the oldest queued run (safe with several workers)."""
    with session_scope(actor=WORKER) as s:
        row = s.execute(
            text(
                "update runs set status = 'running', started_at = now() where id = ("
                "select id from runs where status = 'queued' order by created_at "
                "for update skip locked limit 1) returning id"
            )
        ).first()
    return str(row[0]) if row else None
