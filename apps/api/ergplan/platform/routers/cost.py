"""Today's cost (journey step 2): the bill rebuilt from the approved tariff beside the real one,
and the avoided cost of grid energy block by block. Loads approved rules (invariant 2) and hands
them to the pure engines."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.sourced import RefKind, SourcedValue, SourceRef, derive
from ...core.units import Unit
from ...db.base import session_scope
from ...db.models import Bill, Connection, LoadProfile, Site
from ...engine import avoided_cost, replay
from ...engine import scope as escope
from ...engine.gaps import GAPS
from ...intake import bills as bill_store
from ...intake import profile_synthesis
from ...rulebook import repository
from ...rulebook.service import jurisdiction_chain

router = APIRouter(tags=["cost"])

KINDS_RULE_AND_BILL: list[JsonValue] = [
    "order",
    "regulation",
    "bill",
    "client_stated",
    "assumption",
    "derived",
]


class TariffLineOut(BaseModel):
    code: str
    label: str
    slot: str | None
    amount: SourcedValue = Field(
        json_schema_extra={"owner": "rules.body + bills.billx_result", "ref_kinds": KINDS_RULE_AND_BILL}
    )
    quantity: SourcedValue | None = Field(
        default=None,
        json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill", "client_stated"]},
    )
    rate: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "rules.body", "ref_kinds": ["order", "regulation"]}
    )


BILL_KINDS: list[JsonValue] = ["bill", "client_stated"]


class ReplayLineOut(BaseModel):
    group: str
    label: str
    billed: SourcedValue | None = Field(
        json_schema_extra={"owner": "bills.billx_result", "ref_kinds": BILL_KINDS}
    )
    computed: SourcedValue | None = Field(
        json_schema_extra={"owner": "rules.body + bills.billx_result", "ref_kinds": KINDS_RULE_AND_BILL}
    )
    difference: SourcedValue | None = Field(
        json_schema_extra={"owner": "rules.body + bills.billx_result", "ref_kinds": KINDS_RULE_AND_BILL}
    )
    status: str
    explanation: str
    gap: str | None
    billed_items: list[str]


class ReplayOut(BaseModel):
    bill_id: str
    bill_month: date | None
    evaluated_on: date
    status: str
    schedule: str | None
    tod: str | None
    computed_total: SourcedValue | None = Field(
        json_schema_extra={"owner": "rules.body + bills.billx_result", "ref_kinds": KINDS_RULE_AND_BILL}
    )
    billed_total: SourcedValue | None = Field(
        json_schema_extra={"owner": "bills.billx_result", "ref_kinds": BILL_KINDS}
    )
    total_difference: SourcedValue | None = Field(
        json_schema_extra={"owner": "rules.body + bills.billx_result", "ref_kinds": KINDS_RULE_AND_BILL}
    )
    lines: list[ReplayLineOut]
    tariff_lines: list[TariffLineOut]
    gaps: dict[str, str]
    notes: list[str]
    file_url: str


def _facts(s: Session, conn: Connection) -> escope.ConnectionFacts:
    site = s.get(Site, conn.site_id)
    if conn.tariff_category is None or conn.voltage_kv is None or site is None:
        raise HTTPException(422, "the connection needs a tariff category and supply voltage")
    return escope.ConnectionFacts(
        discom=conn.discom_id,
        state=site.state,
        category=conn.tariff_category,
        voltage_kv=conn.voltage_kv,
        connection_kind=conn.connection_kind,
        contract_demand_kva=conn.contract_demand_kva,
        rate_block=conn.rate_block,
    )


def _rules_for(
    s: Session, facts: escope.ConnectionFacts, as_of: date | None = None
) -> Callable[[date], avoided_cost.MonthRules]:
    """Rules for a month. With `as_of`, the versions in force on that date (the tariff a plan faces)
    with the month choosing seasonal and ToD rows; without, the versions in force on the date itself
    (a bill's own period)."""
    chain = jurisdiction_chain(s, facts.discom)
    cache: dict[date, avoided_cost.MonthRules] = {}

    def get(on: date) -> avoided_cost.MonthRules:
        if on not in cache:
            ctx = escope.context(facts, on)
            when = as_of or on
            ts = repository.approved_rules(s, "tariff_schedule", chain, when)
            td = repository.approved_rules(s, "tod_slots", chain, when)
            cache[on] = avoided_cost.MonthRules(escope.first(ts, ctx, chain), escope.first(td, ctx, chain))
        return cache[on]

    return get


def _cd(conn: Connection) -> SourcedValue | None:
    if conn.contract_demand_kva is None:
        return None
    p = (conn.provenance or {}).get("contract_demand_kva") or {}
    raw = p.get("source_ref") or {"kind": "client_stated"}
    ref = SourceRef.model_validate({k: v for k, v in raw.items() if k != "url"})
    return SourcedValue(
        value=conn.contract_demand_kva, unit=Unit.KVA, source_refs=(ref,), label="Contract demand"
    )


def _bill_date(b: Bill, confirmed: dict[str, str]) -> date:
    f = bill_store._bill_facts(b)
    to = confirmed.get("period.to") or f.text("period.to")
    try:
        if to and len(to) >= 10:
            return date.fromisoformat(to[:10])
    except ValueError:
        pass
    if b.bill_month is None:
        raise HTTPException(422, f"bill {b.id} has no period or month")
    return b.bill_month


def _billed(bill_id: str, ln: replay.ReplayLine) -> SourcedValue | None:
    """What the bill charged for a line group, citing billx's element for each printed line."""
    if ln.billed is None:
        return None
    refs = tuple(
        SourceRef(kind=RefKind.BILL, bill_id=bill_id, field_path=f"elements.{i}.amount")
        for i in ln.billed_indices
    ) or (SourceRef(kind=RefKind.BILL, bill_id=bill_id, field_path="elements"),)
    return SourcedValue(value=ln.billed, unit=Unit.INR, source_refs=refs, label=f"{ln.label} (bill)")


def _difference(
    computed: SourcedValue | None, billed: list[SourcedValue | None], label: str
) -> SourcedValue | None:
    inputs = [x for x in [computed, *billed] if x is not None]
    if not inputs:
        return None
    value = (computed.value if computed else Decimal(0)) - sum((x.value for x in billed if x), Decimal(0))
    return derive(value, Unit.INR, inputs, label=label)


def _replay_out(
    s: Session, conn: Connection, b: Bill, rules: Callable[[date], avoided_cost.MonthRules]
) -> ReplayOut:
    conf = {c.path: c.value for c in bill_store._confirmations(s, b.id).values() if c.value is not None}
    when = _bill_date(b, conf)
    mr = rules(when)
    bill = next(x for x in b.billx_result.get("bills", []) if int(x.get("index", 0)) == b.bill_index)
    r = replay.replay(b.id, bill, conf, when, mr.schedule, mr.tod, _cd(conn))
    gaps = {
        g: GAPS[g]
        for g in dict.fromkeys([ln.gap for ln in r.lines if ln.gap] + (r.tariff.gaps if r.tariff else []))
    }
    return ReplayOut(
        bill_id=b.id,
        bill_month=b.bill_month,
        evaluated_on=when,
        status=r.status,
        schedule=mr.schedule.label if mr.schedule else None,
        tod=mr.tod.label if mr.tod else None,
        computed_total=r.computed_total,
        billed_total=None
        if r.billed_total is None
        else SourcedValue(
            value=r.billed_total,
            unit=Unit.INR,
            label="Current charges (bill)",
            source_refs=(SourceRef(kind=RefKind.BILL, bill_id=b.id, field_path="totals.current_charges"),),
        ),
        total_difference=_difference(
            r.computed_total, [_billed(b.id, ln) for ln in r.lines], "Rebuilt − billed"
        ),
        lines=[
            ReplayLineOut(
                group=ln.group,
                label=ln.label,
                billed=_billed(b.id, ln),
                computed=ln.computed,
                difference=_difference(ln.computed, [_billed(b.id, ln)], f"{ln.label}: rebuilt − billed"),
                status=ln.status,
                explanation=ln.explanation,
                gap=ln.gap,
                billed_items=ln.billed_items,
            )
            for ln in r.lines
        ],
        tariff_lines=[
            TariffLineOut(
                code=t.code, label=t.label, slot=t.slot, amount=t.amount, quantity=t.quantity, rate=t.rate
            )
            for t in (r.tariff.lines if r.tariff else [])
        ],
        gaps=gaps,
        notes=r.notes,
        file_url=f"/bills/{b.id}/file",
    )


@router.get("/connections/{connection_id}/replay", response_model=list[ReplayOut])
def connection_replay(connection_id: str) -> list[ReplayOut]:
    with session_scope() as s:
        conn = s.get(Connection, connection_id)
        if conn is None:
            raise HTTPException(404, "connection not found")
        rules = _rules_for(s, _facts(s, conn))
        bills = s.scalars(
            select(Bill)
            .where(Bill.connection_id == conn.id, Bill.accepted.is_(True))
            .order_by(Bill.bill_month)
        ).all()
        return [_replay_out(s, conn, b, rules) for b in bills]


class RateCardOut(BaseModel):
    month: date
    slot: str | None
    components: list[SourcedValue] = Field(
        json_schema_extra={"owner": "rules.body", "ref_kinds": ["order", "regulation", "derived"]}
    )
    kvah_factor: SourcedValue | None = Field(
        json_schema_extra={
            "owner": "bills.billx_result",
            "ref_kinds": ["bill", "assumption", "client_stated"],
        }
    )
    rate: SourcedValue = Field(
        json_schema_extra={"owner": "rules.body + bills.billx_result", "ref_kinds": KINDS_RULE_AND_BILL}
    )


class AvoidedOut(BaseModel):
    connection_id: str
    profile_version: int
    profile_provenance: str
    year_start: date
    tariff_as_of: date
    matrix: list[list[int]]  # 12 × 96 indices into `cards`: every cell's rate is a cited SourcedValue
    cards: list[RateCardOut]
    annual: list[SourcedValue] = Field(
        json_schema_extra={
            "owner": "rules.body + load_profiles.series_kw",
            "ref_kinds": [*KINDS_RULE_AND_BILL, "measured"],
        }
    )
    gaps: dict[str, str]
    notes: list[str]


def _kvah_factor(s: Session, conn: Connection) -> tuple[SourcedValue, SourcedValue]:
    """kVAh per kWh and the power factor, from the connection's accepted bills (kVAh/kWh where both
    are printed), else the bills' power factor, else an assumption of 0.95."""
    ratios: list[tuple[Decimal, list[SourceRef]]] = []
    pfs: list[tuple[Decimal, SourceRef]] = []
    for b in s.scalars(select(Bill).where(Bill.connection_id == conn.id, Bill.accepted.is_(True))):
        v = bill_store.values(s, b)
        kwh, kvah, pf = v.get("energy.kwh"), v.get("energy.kvah"), v.get("energy.power_factor")
        if kwh and kvah and kwh.dec and kvah.dec and kwh.dec > 0 and kvah.dec >= kwh.dec:
            ratios.append((kvah.dec / kwh.dec, [kwh.ref, kvah.ref]))
        if pf and pf.dec and Decimal("0.3") <= pf.dec <= 1:
            pfs.append((pf.dec, pf.ref))
    if ratios:
        r = sum((x for x, _ in ratios), Decimal(0)) / len(ratios)
        refs = tuple(ref for _, rs in ratios for ref in rs)
        f = SourcedValue(value=r, unit=Unit.RATIO, source_refs=refs, label="kVAh per kWh (bills)")
        return f, SourcedValue(value=1 / r, unit=Unit.RATIO, source_refs=refs, label="Power factor (bills)")
    if pfs:
        p = sum((x for x, _ in pfs), Decimal(0)) / len(pfs)
        refs2 = tuple(ref for _, ref in pfs)
        return (
            SourcedValue(value=1 / p, unit=Unit.RATIO, source_refs=refs2, label="kVAh per kWh (1 / PF)"),
            SourcedValue(value=p, unit=Unit.RATIO, source_refs=refs2, label="Power factor (bills)"),
        )
    a = SourceRef(kind=RefKind.ASSUMPTION, note="no bill gives kVAh and kWh or a power factor; 0.95 assumed")
    return (
        SourcedValue(value=1 / Decimal("0.95"), unit=Unit.RATIO, source_refs=(a,), label="kVAh per kWh"),
        SourcedValue(value=Decimal("0.95"), unit=Unit.RATIO, source_refs=(a,), label="Power factor"),
    )


@router.get("/connections/{connection_id}/avoided-cost", response_model=AvoidedOut)
def connection_avoided_cost(
    connection_id: str,
    version: Annotated[int | None, Query()] = None,
    as_of: Annotated[date | None, Query(description="tariff in force on this date; default today")] = None,
) -> AvoidedOut:
    with session_scope() as s:
        conn = s.get(Connection, connection_id)
        if conn is None:
            raise HTTPException(404, "connection not found")
        q = select(LoadProfile).where(LoadProfile.connection_id == conn.id)
        q = q.where(LoadProfile.version == version) if version else q.order_by(LoadProfile.version.desc())
        lp = s.scalars(q).first()
        if lp is None:
            raise HTTPException(404, "no load profile for this connection")
        kw = profile_synthesis.decode(lp.series_kw)
        kind = RefKind.MEASURED if lp.provenance == "measured" else RefKind.DERIVED
        pref = SourcedValue(
            value=sum(kw, Decimal(0)) * Decimal("0.25"),
            unit=Unit.KWH,
            label="Profile energy (year)",
            source_refs=(SourceRef(kind=kind, note=f"load profile v{lp.version} ({lp.provenance})"),),
        )
        factor, pf = _kvah_factor(s, conn)
        wf = avoided_cost.build(
            lp.year_start,
            kw,
            _rules_for(s, _facts(s, conn), as_of or date.today()),
            factor,
            pref,
            _cd(conn),
            pf,
        )
        return AvoidedOut(
            connection_id=conn.id,
            profile_version=lp.version,
            profile_provenance=lp.provenance,
            year_start=wf.year_start,
            tariff_as_of=as_of or date.today(),
            matrix=wf.cell_cards,
            cards=[
                RateCardOut(
                    month=c.month,
                    slot=c.slot,
                    components=c.components,
                    kvah_factor=c.kvah_factor,
                    rate=c.rate_inr_per_kwh,
                )
                for c in wf.cards
            ],
            annual=wf.annual,
            gaps={g: GAPS[g] for g in wf.gaps},
            notes=wf.notes,
        )
