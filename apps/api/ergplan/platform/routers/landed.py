"""Landed costs (journey step 3): every source's waterfall per ToD slot at the meter, beside the
avoided cost of grid energy, and the regulatory limits for the connection. Loads approved rules
and prices; the arithmetic is in engine.landed_cost (pure)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.sourced import RefKind, SourcedValue, SourceRef, derive
from ...core.units import Unit
from ...db.base import session_scope
from ...db.models import Asset, Connection, PricePoint, PriceVintage
from ...engine import avoided_cost, landed_cost, lcoe
from ...engine import scope as escope
from ...engine.gaps import GAPS
from ...engine.tariff_eval import slot_of
from ...rulebook import repository
from ...rulebook.models import RuleView
from ...rulebook.scope import matches
from ...rulebook.service import jurisdiction_chain
from .cost import _facts, _kvah_factor, _rules_for

router = APIRouter(tags=["landed cost"])

ALL_KINDS: list[JsonValue] = [
    "order",
    "regulation",
    "bill",
    "client_stated",
    "assumption",
    "derived",
    "market",
]

# Normative PPA prices at the generator bus (INR/kWh), assumptions until the client states a quote.
DEFAULT_PRICE = {
    "oa_solar_intra": ("3.10", "intra-state solar PPA, 2026 tenders and C&I offers in UP and Maharashtra"),
    "oa_wind_intra": ("3.60", "intra-state wind PPA, 2026"),
    "oa_hybrid_intra": ("3.50", "intra-state solar-wind hybrid PPA, 2026"),
    "oa_solar_ists": ("2.70", "ISTS-connected solar PPA, 2026 auctions"),
    "oa_wind_ists": ("3.30", "ISTS-connected wind PPA, 2026 auctions"),
    "oa_hybrid_ists": ("3.30", "ISTS-connected hybrid PPA, 2026 auctions"),
    "oa_bess": ("4.80", "storage-backed (peak) supply tariff, 2026"),
    "pumped_storage": ("5.20", "pumped-storage supply tariff, 2026"),
    "group_captive": ("3.10", "group-captive solar PPA before the equity cost"),
}
DEFAULT_OWNERSHIP = {"group_captive": "group_captive"}


class SourceScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_inr_per_kwh: Decimal | None = None
    ownership: str | None = Field(default=None, pattern="^(captive|group_captive|third_party)$")
    commissioned: date | None = None
    capacity_mw: Decimal | None = None
    cuf_pct: Decimal | None = None
    equity_cost_inr_per_kwh: Decimal | None = None


class ScenarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: int | None = Field(default=None, ge=1, le=12)
    as_of: date | None = None
    geoa: bool = False
    sources: dict[str, SourceScenario] = Field(default_factory=dict)


class SlotOut(BaseModel):
    name: str
    start: str
    end: str


class SlotWaterfall(BaseModel):
    slot: str
    lines: list[SourcedValue] = Field(
        json_schema_extra={"owner": "rules.body + price_series + scenario", "ref_kinds": ALL_KINDS}
    )
    total: SourcedValue = Field(
        json_schema_extra={"owner": "rules.body + price_series + scenario", "ref_kinds": ALL_KINDS}
    )


class SourceOut(BaseModel):
    id: str
    label: str
    available: bool
    reason: str | None = None
    by_slot: list[SlotWaterfall]
    gaps: list[str]
    notes: list[str]
    rules_used: list[str]


class AvoidedSlot(BaseModel):
    slot: str
    rate: SourcedValue = Field(
        json_schema_extra={"owner": "rules.body + bills.billx_result", "ref_kinds": ALL_KINDS}
    )


class LimitOut(BaseModel):
    limit: str
    value: SourcedValue = Field(
        json_schema_extra={"owner": "rules.body", "ref_kinds": ["order", "regulation"]}
    )
    label: str | None


class LandedOut(BaseModel):
    connection_id: str
    as_of: date
    month: int
    slots: list[SlotOut]
    avoided: list[AvoidedSlot]
    sources: list[SourceOut]
    limits: list[LimitOut]
    gaps: dict[str, str]


def _overlaps_daylight(start: str, end: str) -> bool:
    """Whether a slot overlaps 07:00–17:00 (slots may wrap past midnight)."""

    def m(t: str) -> int:
        h, mi = t.split(":")
        return int(h) * 60 + int(mi)

    a, b = m(start), m(end)
    spans = [(a, b)] if a < b else [(a, 1440), (0, b)]
    return any(x < 17 * 60 and y > 7 * 60 for x, y in spans)


def _assumed(value: str, unit: Unit, note: str, label: str) -> SourcedValue:
    return SourcedValue(
        value=Decimal(value),
        unit=unit,
        label=label,
        source_refs=(SourceRef(kind=RefKind.ASSUMPTION, note=note),),
    )


def _stated(value: Decimal, unit: Unit, label: str) -> SourcedValue:
    return SourcedValue(
        value=value, unit=unit, label=label, source_refs=(SourceRef(kind=RefKind.CLIENT_STATED),)
    )


def _iex_slot_prices(
    s: Session, segment: str, month: int, tod: RuleView | None, slot_names: list[str]
) -> dict[str, SourcedValue] | None:
    v = s.scalars(
        select(PriceVintage)
        .where(PriceVintage.segment == segment, PriceVintage.superseded_by.is_(None))
        .order_by(PriceVintage.date_to.desc())
    ).first()
    if v is None:
        return None
    rows = s.execute(
        select(PricePoint.block, func.avg(PricePoint.mcp_inr_per_mwh))
        .where(PricePoint.vintage_id == v.id, func.extract("month", PricePoint.day) == month)
        .group_by(PricePoint.block)
    ).all()
    if not rows:
        return None
    by_block = {int(b): Decimal(str(p)) for b, p in rows}
    out: dict[str, SourcedValue] = {}
    for name in slot_names:
        blocks = [
            b
            for b in by_block
            if tod is None or (slot_of(tod, month, (b - 1) * 15) or {}).get("name") == name
        ]
        if not blocks:
            continue
        mean = sum((by_block[b] for b in blocks), Decimal(0)) / len(blocks) / 1000
        out[name] = SourcedValue(
            value=mean.quantize(Decimal("0.0001")),
            unit=Unit.INR_PER_KWH,
            label=f"IEX {segment.upper()} MCP",
            source_refs=(
                SourceRef(
                    kind=RefKind.MARKET,
                    vintage_id=v.id,
                    note=f"mean clearing price, {name}, month {month}, {v.filename} "
                    f"({v.date_from} to {v.date_to})",
                ),
            ),
        )
    return out


@router.get("/connections/{connection_id}/landed-cost", response_model=LandedOut)
def connection_landed_cost(
    connection_id: str, scenario: Annotated[str | None, Query(description="ScenarioIn as JSON")] = None
) -> LandedOut:
    try:
        sc_in = ScenarioIn.model_validate(json.loads(scenario)) if scenario else ScenarioIn()
    except (ValueError, ValidationError) as e:
        raise HTTPException(422, f"scenario: {e}") from e
    bad = [k for k in sc_in.sources if k not in landed_cost.SOURCE_BY_ID]
    if bad:
        raise HTTPException(422, f"unknown sources: {', '.join(bad)}")
    as_of = sc_in.as_of or date.today()
    month = sc_in.month or as_of.month
    with session_scope() as s:
        conn = s.get(Connection, connection_id)
        if conn is None:
            raise HTTPException(404, "connection not found")
        facts = _facts(s, conn)
        chain = jurisdiction_chain(s, facts.discom)
        mdate = date(as_of.year if month >= as_of.month else as_of.year + 1, month, 15)
        mr = _rules_for(s, facts, as_of)(mdate)
        factor, _pf = _kvah_factor(s, conn)
        slot_names: list[str] = []
        slots: list[SlotOut] = []
        if mr.tod is not None:
            for sl in mr.tod.body.get("slots", []):
                if not sl.get("months") or month in sl["months"]:
                    slots.append(SlotOut(name=str(sl["name"]), start=str(sl["start"]), end=str(sl["end"])))
                    slot_names.append(str(sl["name"]))
        if not slot_names:
            slot_names = ["all hours"]
            slots = [SlotOut(name="all hours", start="00:00", end="24:00")]
        cards: dict[str, SourcedValue] = {}
        if mr.schedule is not None:
            for i, sl in enumerate(mr.tod.body.get("slots", []) if mr.tod else [None]):
                name = str(sl["name"]) if sl else "all hours"
                if name not in slot_names:
                    continue
                card = avoided_cost.rate_card(mdate, mr, i if sl else None, factor, conn.contract_demand_kva)
                if card is not None:
                    cards[name] = card.rate_inr_per_kwh
        ctx = escope.context(facts, mdate)
        oa_rows = repository.approved_rules(s, "oa_charge", chain, as_of)
        settlements = repository.approved_rules(s, "settlement", chain, as_of)
        waivers = repository.approved_rules(s, "ists_waiver", chain, as_of)
        limits_rows = repository.approved_rules(s, "regulatory_limit", chain, as_of)
        assets = s.scalars(select(Asset).where(Asset.site_id == conn.site_id)).all()
        all_gaps: set[str] = set()
        sources: list[SourceOut] = []
        for spec in landed_cost.SOURCES:
            o = sc_in.sources.get(spec.id, SourceScenario())
            ownership = o.ownership or DEFAULT_OWNERSHIP.get(spec.id, "third_party")
            notes: list[str] = []
            prices: dict[str, SourcedValue] = {}
            extra: tuple[SourcedValue, ...] = ()
            reason = None
            if spec.price_kind == "grid":
                prices = dict(cards)
                reason = None if cards else "no approved tariff for this connection"
            elif spec.price_kind == "green_tariff":
                prem = mr.schedule.get("/green_tariff_premium_inr_per_unit") if mr.schedule else None
                if prem in (None, "") or mr.schedule is None:
                    reason = "the DISCOM's green-tariff premium is not in the approved schedule"
                    all_gaps.add("green_tariff")
                else:
                    p = SourcedValue(
                        value=Decimal(str(prem)) * factor.value,
                        unit=Unit.INR_PER_KWH,
                        source_refs=(
                            mr.schedule.ref("/green_tariff_premium_inr_per_unit"),
                            *factor.source_refs,
                        ),
                        label="Green-tariff premium",
                    )
                    prices = dict(cards)
                    extra = (p,)
            elif spec.price_kind == "lcoe":
                v = (
                    _stated(o.price_inr_per_kwh, Unit.INR_PER_KWH, "Rooftop solar price")
                    if o.price_inr_per_kwh
                    else lcoe.lcoe(lcoe.default_rooftop())
                )
                day = [sl.name for sl in slots if _overlaps_daylight(sl.start, sl.end)]
                prices = {n: v for n in day}
                notes.append(
                    "rooftop energy comes only in daylight (07:00–17:00 assumed); other slots take none"
                )
            elif spec.price_kind == "lcos":
                st = lcoe.default_bess()
                v = lcoe.lcos(st)
                if cards:
                    cheapest_name = min(cards, key=lambda n: cards[n].value)
                    charge = derive(
                        cards[cheapest_name].value / (st.round_trip_pct.value / 100),
                        Unit.INR_PER_KWH,
                        [cards[cheapest_name], st.round_trip_pct],
                        label=f"Energy charged in the {cheapest_name} slot ÷ round-trip efficiency",
                    )
                    extra = (charge,)
                    prices = {n: v for n in slot_names if n != cheapest_name}
                else:
                    reason = "no approved tariff to charge the battery from"
            elif spec.price_kind == "iex":
                got = _iex_slot_prices(s, spec.iex_segment or "", month, mr.tod, slot_names)
                if not got:
                    reason = f"no {str(spec.iex_segment).upper()} prices loaded"
                    all_gaps.add("iex_prices")
                else:
                    prices = got
            elif spec.price_kind == "thermal":
                th = next((a for a in assets if a.kind == "captive_thermal"), None)
                if th is None:
                    reason = "no captive thermal plant on this site"
                elif th.params.get("variable_cost_inr_per_kwh"):
                    v = _stated(
                        Decimal(str(th.params["variable_cost_inr_per_kwh"])),
                        Unit.INR_PER_KWH,
                        "Thermal variable cost",
                    )
                    prices = {n: v for n in slot_names}
                else:
                    reason = "the thermal plant's variable cost is not stated"
            else:  # ppa
                if o.price_inr_per_kwh is not None:
                    v = _stated(o.price_inr_per_kwh, Unit.INR_PER_KWH, "PPA tariff")
                else:
                    val, note = DEFAULT_PRICE[spec.id]
                    v = _assumed(val, Unit.INR_PER_KWH, f"{note}; change it to your quote", "PPA tariff")
                prices = {n: v for n in slot_names}
                if spec.id == "group_captive":
                    eq = (
                        _stated(o.equity_cost_inr_per_kwh, Unit.INR_PER_KWH, "Equity cost")
                        if o.equity_cost_inr_per_kwh is not None
                        else _assumed(
                            "0.25",
                            Unit.INR_PER_KWH,
                            "26% equity in the generating company, carried over its life, per kWh consumed",
                            "Equity cost (group captive)",
                        )
                    )
                    extra = (eq,)
            scn_common = dict(
                ownership=ownership,
                commissioned=o.commissioned,
                on=as_of,
                geoa=sc_in.geoa,
                extra=extra,
                capacity_mw=_stated(o.capacity_mw, Unit.MW, "Capacity") if o.capacity_mw else None,
                cuf_pct=_stated(o.cuf_pct, Unit.PERCENT, "CUF") if o.cuf_pct else None,
            )
            src_ctx = {**ctx, "connection": spec.connection, "source": spec.source, "ownership": ownership}
            settlement = next((r for r in settlements if matches(r.scope, src_ctx)), None)
            by_slot: list[SlotWaterfall] = []
            gaps: list[str] = []
            used: list[str] = []
            for name in slot_names:
                if name not in prices:
                    continue
                wf = landed_cost.evaluate(
                    spec,
                    ctx,
                    landed_cost.Scenario(price=prices[name], **scn_common),  # type: ignore[arg-type]
                    oa_rows,
                    waivers,
                    settlement,
                )
                by_slot.append(SlotWaterfall(slot=name, lines=wf.lines, total=wf.total))
                gaps += wf.gaps
                notes += wf.notes
                used += wf.rules_used
            gaps = list(dict.fromkeys(gaps))
            all_gaps.update(gaps)
            sources.append(
                SourceOut(
                    id=spec.id,
                    label=spec.label,
                    available=bool(by_slot),
                    reason=reason,
                    by_slot=by_slot,
                    gaps=gaps,
                    notes=list(dict.fromkeys(notes)),
                    rules_used=list(dict.fromkeys(used)),
                )
            )
        lim_ctx = {**ctx}
        limits = []
        for r in limits_rows:
            if matches(r.scope, lim_ctx):
                unit = {
                    "percent": Unit.PERCENT,
                    "mw": Unit.MW,
                    "kw": Unit.KW,
                    "kva": Unit.KVA,
                    "hours": Unit.HOURS,
                    "count": Unit.COUNT,
                }[str(r.body["unit"])]
                limits.append(
                    LimitOut(
                        limit=str(r.body["limit"]),
                        label=r.label,
                        value=SourcedValue(
                            value=Decimal(str(r.body["value"])),
                            unit=unit,
                            source_refs=(r.ref("/value"),),
                            label=r.label,
                        ),
                    )
                )
        if not limits_rows:
            all_gaps.add("regulatory_limits")
        return LandedOut(
            connection_id=conn.id,
            as_of=as_of,
            month=month,
            slots=slots,
            avoided=[AvoidedSlot(slot=n, rate=cards[n]) for n in slot_names if n in cards],
            sources=sources,
            limits=limits,
            gaps={g: GAPS[g] for g in sorted(all_gaps) if g in GAPS},
        )


@router.get("/rulebooks/limits", response_model=list[LimitOut])
def limits(connection_id: str, as_of: date | None = None) -> list[LimitOut]:
    """Regulatory limits (RE cap, storage mandate, minimum OA size and contract demand) that apply."""
    out = connection_landed_cost(connection_id, json.dumps({"as_of": (as_of or date.today()).isoformat()}))
    return out.limits
