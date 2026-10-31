"""Settlement (Stage 5): settle a dispatch of sources against the connection's load profile under the
approved settlement rule. Analyst endpoint until the plan (Stage 7) shows the client a statement."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ...core.sourced import RefKind, SourcedValue, SourceRef
from ...core.units import Unit
from ...db.base import session_scope
from ...db.models import Connection, LoadProfile, Site
from ...engine import landed_cost
from ...engine import scope as escope
from ...engine.tariff_eval import slot_adjustment_pct, slot_of
from ...intake import generation, profile_synthesis
from ...rulebook import repository
from ...rulebook.scope import matches
from ...rulebook.service import jurisdiction_chain
from ...settlement.simulate import Block, SourceIn, simulate, statement
from ..auth import Caller, analyst
from .cost import _facts, _rules_for

router = APIRouter(tags=["settlement"])
CATEGORY = {
    "captive": "captive_generation",
    "group_captive": "captive_generation",
    "third_party": "bilateral",
}


class DispatchSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern="^[a-z0-9_]{1,32}$")
    kind: str  # a landed-cost source id: oa_solar_intra, oa_wind_ists, …
    capacity_mw: Decimal = Field(gt=0)
    ownership: str = Field(default="captive", pattern="^(captive|group_captive|third_party)$")
    kw: list[Decimal] | None = None  # 15-minute injection at the generator; a normative curve when absent


class DispatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[DispatchSource] = Field(min_length=1, max_length=12)
    as_of: date | None = None
    lapse_price_inr_per_kwh: Decimal | None = None


class MonthOut(BaseModel):
    month: date
    consumption: str
    setoff: dict[str, str]
    banked: str
    charge: str
    withdrawn: str
    lapsed: str
    grid: str
    unbanked: str
    balances: dict[str, str]


class SettleOut(BaseModel):
    connection_id: str
    rule: str | None
    granularity: str
    profile_version: int
    sources: list[dict[str, Any]]
    statement: list[SourcedValue] = Field(
        json_schema_extra={
            "owner": "rules.body + load_profiles.series_kw",
            "ref_kinds": ["order", "regulation", "derived", "assumption", "client_stated", "measured"],
        }
    )
    months: list[MonthOut]
    notes: list[str]


@router.post("/connections/{connection_id}/settle", response_model=SettleOut)
def settle(connection_id: str, body: DispatchIn, who: Annotated[Caller, Depends(analyst)]) -> SettleOut:
    del who
    as_of = body.as_of or date.today()
    with session_scope() as s:
        conn = s.get(Connection, connection_id)
        if conn is None:
            raise HTTPException(404, "connection not found")
        site = s.get(Site, conn.site_id)
        assert site is not None
        lp = s.scalars(
            select(LoadProfile)
            .where(LoadProfile.connection_id == conn.id)
            .order_by(LoadProfile.version.desc())
        ).first()
        if lp is None:
            raise HTTPException(404, "no load profile for this connection")
        kw = profile_synthesis.decode(lp.series_kw)
        facts = _facts(s, conn)
        chain = jurisdiction_chain(s, facts.discom)
        rules = _rules_for(s, facts, as_of)
        oa_rows = repository.approved_rules(s, "oa_charge", chain, as_of)
        settlements = repository.approved_rules(s, "settlement", chain, as_of)
        days = profile_synthesis.year_days(lp.year_start)
        notes: list[str] = []
        sources: list[SourceIn] = []
        supply: dict[str, list[Decimal]] = {}
        info: list[dict[str, Any]] = []
        rule = None
        for d in body.sources:
            spec = landed_cost.SOURCE_BY_ID.get(d.kind)
            if spec is None or not spec.open_access:
                raise HTTPException(422, f"{d.kind} is not an open-access source")
            if d.kw is not None and len(d.kw) != len(kw):
                raise HTTPException(422, f"{d.id}: {len(kw)} 15-minute values are needed")
            cap_kw = d.capacity_mw * 1000
            if d.kw is not None:
                inj, cuf = d.kw, None
            else:
                try:
                    inj, cuf = generation.profile(
                        generation.curve_for(spec.source, site.state), cap_kw, lp.year_start
                    )
                except generation.CurveNotFound as e:
                    raise HTTPException(
                        422, f"no generation curve {e} for {spec.source} in {site.state}"
                    ) from e
                notes.append(
                    f"{d.id}: normative {spec.source} curve for {site.state} at {cuf}% CUF (assumption)"
                )
            ctx = escope.context(facts, date(as_of.year, as_of.month, 1))
            price = SourcedValue(
                value=Decimal(0),
                unit=Unit.INR_PER_KWH,
                source_refs=(SourceRef(kind=RefKind.ASSUMPTION, note="price not needed to settle"),),
            )
            wf = landed_cost.evaluate(
                spec, ctx, landed_cost.Scenario(price=price, ownership=d.ownership, on=as_of), oa_rows
            )
            keep = wf.delivered.value if wf.delivered else Decimal(1)
            supply[d.id] = [v * keep * Decimal("0.25") for v in inj]
            src_ctx = {**ctx, "connection": spec.connection, "source": spec.source, "ownership": d.ownership}
            own_rule = next((r for r in settlements if matches(r.scope, src_ctx)), None)
            if rule is None and own_rule is not None:
                rule = own_rule
            sources.append(
                SourceIn(
                    id=d.id,
                    category=CATEGORY[d.ownership],
                    may_bank=own_rule is not None and own_rule.id == (rule.id if rule else None),
                )
            )
            info.append(
                {
                    "id": d.id,
                    "kind": d.kind,
                    "capacity_mw": format(d.capacity_mw, "f"),
                    "delivered_share": format(keep, "f"),
                    "injected_kwh": format(sum(inj, Decimal(0)) * Decimal("0.25"), "f"),
                    "settlement_rule": own_rule.label if own_rule else None,
                }
            )
        blocks: list[Block] = []
        tod_cache: dict[int, Any] = {}
        for i, v in enumerate(kw):
            day = days[i // 96]
            first = date(day.year, day.month, 1)
            if day.month not in tod_cache:
                tod_cache[day.month] = rules(first).tod
            tod = tod_cache[day.month]
            sl = slot_of(tod, day.month, (i % 96) * 15) if tod else None
            name = str(sl["name"]) if sl else "all hours"
            cls = frozenset({"peak" if sl and slot_adjustment_pct(sl) > 0 else "off_peak"})
            blocks.append(
                Block(
                    month=first,
                    slot=name,
                    classes=cls,
                    load_kwh=v * Decimal("0.25"),
                    supply_kwh={k: supply[k][i] for k in supply},
                    hour=i // 4,
                )
            )
        res = simulate(blocks, sources, rule)
        load_ref = SourcedValue(
            value=sum((b.load_kwh for b in blocks), Decimal(0)),
            unit=Unit.KWH,
            label="Load profile energy",
            source_refs=(
                SourceRef(
                    kind=RefKind.MEASURED if lp.provenance == "measured" else RefKind.DERIVED,
                    note=f"load profile v{lp.version} ({lp.provenance})",
                ),
            ),
        )
        supply_refs = {
            k: SourcedValue(
                value=sum(v, Decimal(0)),
                unit=Unit.KWH,
                label=f"{k} delivered",
                source_refs=(
                    SourceRef(
                        kind=RefKind.ASSUMPTION if any(x["id"] == k for x in info) else RefKind.CLIENT_STATED,
                        note=f"{k}: injection × delivered share after losses",
                    ),
                ),
            )
            for k, v in supply.items()
        }
        lapse_price = (
            SourcedValue(
                value=body.lapse_price_inr_per_kwh,
                unit=Unit.INR_PER_KWH,
                source_refs=(SourceRef(kind=RefKind.CLIENT_STATED),),
            )
            if body.lapse_price_inr_per_kwh is not None
            else None
        )
        lines = statement(res, rule, load_ref, supply_refs, lapse_price)
        months: list[MonthOut] = []
        idx_by_month: dict[date, list[int]] = {}
        for i, b in enumerate(blocks):
            idx_by_month.setdefault(b.month, []).append(i)
        for m, idx in idx_by_month.items():

            def tot(series: list[Decimal], idx: list[int] = idx) -> str:
                return format(sum((series[i] for i in idx), Decimal(0)).quantize(Decimal("0.001")), "f")

            months.append(
                MonthOut(
                    month=m,
                    consumption=format(
                        sum((blocks[i].load_kwh for i in idx), Decimal(0)).quantize(Decimal("0.001")), "f"
                    ),
                    setoff={k: tot(v) for k, v in res.setoff_kwh.items()},
                    banked=format(
                        sum(
                            (sum((v[i] for i in idx), Decimal(0)) for v in res.deposit_kwh.values()),
                            Decimal(0),
                        ).quantize(Decimal("0.001")),
                        "f",
                    ),
                    charge=format(
                        sum(
                            (sum((v[i] for i in idx), Decimal(0)) for v in res.charge_kwh.values()),
                            Decimal(0),
                        ).quantize(Decimal("0.001")),
                        "f",
                    ),
                    withdrawn=tot(res.withdrawn_kwh),
                    lapsed=format(
                        sum((x["kwh"] for x in res.lapsed if x["month"] == m), Decimal(0)).quantize(
                            Decimal("0.001")
                        ),
                        "f",
                    ),
                    grid=tot(res.grid_kwh),
                    unbanked=format(
                        sum(
                            (sum((v[i] for i in idx), Decimal(0)) for v in res.unbanked_kwh.values()),
                            Decimal(0),
                        ).quantize(Decimal("0.001")),
                        "f",
                    ),
                    balances={
                        x["bucket"]: format(x["kwh"].quantize(Decimal("0.001")), "f")
                        for x in res.balances
                        if x["month"] == m
                    },
                )
            )
        if rule is None:
            notes.append(
                "no approved settlement rule covers these sources: netted block by block, surplus not banked"
            )
        return SettleOut(
            connection_id=conn.id,
            rule=rule.label if rule else None,
            granularity=res.granularity,
            profile_version=lp.version,
            sources=info,
            statement=lines,
            months=months,
            notes=notes,
        )
