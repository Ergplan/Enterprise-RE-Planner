"""What the Evaluate and Results pages need beyond the planning routes: the DISCOMs a client can pick
(with the categories their approved tariff schedules know and what is sourced for their state), the
caller's own evaluations, a site described by typing, and a settled year's dispatch as a file."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.sourced import RefKind, SourcedValue, SourceRef, derive
from ...core.units import Unit
from ...db.base import session_scope
from ...db.models import Bill, Client, Connection, Jurisdiction, LoadProfile, Run, RunResult, Scenario, Site
from ...engine import avoided_cost
from ...intake import defaults, site_intake, typed
from ...rulebook import repository
from ...rulebook.models import RuleView
from ...rulebook.service import UnknownJurisdiction, jurisdiction_chain
from .. import runs as svc
from ..auth import Caller, caller, may_reach

router = APIRouter(tags=["evaluate"])

FAMILIES = ("tariff_schedule", "tod_slots", "oa_charge", "settlement", "regulatory_limit", "ists_waiver")
FAMILY_WORDS = {
    "tariff_schedule": "retail tariff",
    "tod_slots": "time-of-day slots",
    "oa_charge": "open-access charges",
    "settlement": "banking and settlement",
    "regulatory_limit": "open-access limits",
    "ists_waiver": "inter-state charges and waiver",
}


class CategoryOut(BaseModel):
    code: str
    label: str  # the tariff row's label, as the order names it
    voltage_min_kv: str | None
    voltage_max_kv: str | None
    rate_block: str | None
    usual_voltage_kv: str | None


class DiscomOut(BaseModel):
    id: str
    name: str
    state: str
    state_name: str
    categories: list[CategoryOut]
    sourced: dict[str, bool]  # family -> approved and in force today
    ready: bool  # a plan can be computed: a tariff schedule is approved


def _categories(rows: list[RuleView]) -> list[CategoryOut]:
    seen: dict[tuple[str, str | None, str | None, str | None], CategoryOut] = {}
    for r in rows:
        scope = r.scope or {}
        v = scope.get("voltage_kv") or {}
        for code in scope.get("category") or [str(r.body.get("category") or r.label or "")]:
            if not code:
                continue
            key = (
                code,
                str(v.get("min")) if v.get("min") is not None else None,
                str(v.get("max")) if v.get("max") is not None else None,
                scope.get("rate_block"),
            )
            if key in seen:
                continue
            usual = defaults.USUAL_VOLTAGE_KV.get(code)
            seen[key] = CategoryOut(
                code=code,
                label=r.label or code,
                voltage_min_kv=key[1],
                voltage_max_kv=key[2],
                rate_block=scope.get("rate_block"),
                usual_voltage_kv=format(usual, "f") if usual is not None else None,
            )
    return list(seen.values())


@router.get("/intake/discoms", response_model=list[DiscomOut])
def discoms(on: Annotated[date | None, Query()] = None) -> list[DiscomOut]:
    """Every DISCOM ergPLAN knows, with the categories its approved tariff schedule names, what is
    sourced for its state today, and whether a plan can be computed for it yet."""
    when = on or date.today()
    out = []
    with session_scope() as s:
        states = {j.id: j for j in s.scalars(select(Jurisdiction).where(Jurisdiction.kind == "state"))}
        for did, st in sorted(defaults.DISCOM_STATE.items(), key=lambda x: (x[1], x[0])):
            j = s.get(Jurisdiction, did)
            try:
                chain = jurisdiction_chain(s, did)
            except UnknownJurisdiction:
                chain = []
            sourced = {}
            cats: list[CategoryOut] = []
            for fam in FAMILIES:
                rows = repository.approved_rules(s, fam, chain, when) if chain else []
                sourced[fam] = bool(rows)
                if fam == "tariff_schedule":
                    cats = _categories(rows)
            out.append(
                DiscomOut(
                    id=did,
                    name=j.name if j is not None else did.upper(),
                    state=st,
                    state_name=states[st].name if st in states else st,
                    categories=cats,
                    sourced=sourced,
                    ready=sourced["tariff_schedule"],
                )
            )
    return out


class EvaluationOut(BaseModel):
    connection_id: str
    client: str
    site: str
    state: str | None
    discom: str
    category: str | None
    contract_demand_kva: str | None
    bills: int
    profile_provenance: str | None
    created_at: datetime | None
    latest_run: dict[str, Any] | None  # {scenario, status, saving, finished_at}


@router.get("/connections", response_model=list[EvaluationOut])
def list_connections(who: Annotated[Caller, Depends(caller)]) -> list[EvaluationOut]:
    """The caller's evaluations (a client: their own; an analyst: all), newest first."""
    with session_scope() as s:
        rows = s.execute(
            select(Connection, Site, Client)
            .join(Site, Site.id == Connection.site_id)
            .join(Client, Client.id == Site.client_id)
            .order_by(Client.created_at.desc())
        ).all()
        out = []
        for conn, site, client in rows:
            # a client sees their own evaluations (in development too, where the headers are trusted)
            if who.role != "analyst" and not may_reach(s, who, "connection_id", conn.id):
                continue
            prof = s.scalars(
                select(LoadProfile)
                .where(LoadProfile.connection_id == conn.id)
                .order_by(LoadProfile.version.desc())
            ).first()
            latest = None
            run = s.scalars(
                select(Run)
                .join(Scenario, Scenario.id == Run.scenario_id)
                .where(Scenario.connection_id == conn.id, Run.replay_of.is_(None))
                .order_by(Run.created_at.desc())
            ).first()
            if run is not None and (who.role == "analyst" or run.status == "done"):
                sc = s.get(Scenario, run.scenario_id)
                rr = s.get(RunResult, run.id)
                latest = {
                    "scenario": sc.name if sc else None,
                    "scenario_id": run.scenario_id,
                    "run_id": run.id,
                    "status": run.status,
                    "saving": (rr.summary.get("annual", {}).get("saving") if rr else None),
                    "finished_at": run.finished_at,
                }
            n_bills = len(s.scalars(select(Bill.id).where(Bill.connection_id == conn.id)).all())
            out.append(
                EvaluationOut(
                    connection_id=conn.id,
                    client=client.name,
                    site=site.name,
                    state=site.state,
                    discom=conn.discom_id,
                    category=conn.tariff_category,
                    contract_demand_kva=(
                        None if conn.contract_demand_kva is None else format(conn.contract_demand_kva, "f")
                    ),
                    bills=n_bills,
                    profile_provenance=prof.provenance if prof else None,
                    created_at=client.created_at,
                    latest_run=latest,
                )
            )
        return out


@router.post("/intake/typed", response_model=site_intake.SiteIntake)
def intake_typed(body: typed.TypedIn) -> site_intake.SiteIntake:
    """A SiteIntake from typed facts (nothing saved): the year's units spread over twelve months by
    working days, or the months as typed; assumptions marked as such."""
    try:
        return typed.build(body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def _run_for(s: Session, run_id: str, who: Caller) -> tuple[Run, RunResult]:
    run = s.get(Run, run_id)
    if run is None or (who.role != "analyst" and run.status != "done"):
        raise HTTPException(404, "run not found")
    rr = s.get(RunResult, run_id)
    if rr is None:
        raise HTTPException(409, "the run has no result yet")
    return run, rr


@router.get("/runs/{run_id}/dispatch.csv")
def dispatch_csv(run_id: str, who: Annotated[Caller, Depends(caller)]) -> StreamingResponse:
    """The whole settled year, one row per block: time, slot, load and every series in kWh."""
    with session_scope() as s:
        _run, rr = _run_for(s, run_id, who)
        d = svc.read_dispatch(rr.dispatch)
    y0 = date.fromisoformat(d["year_start"])
    step = timedelta(minutes=int(d["minutes"]))
    t0 = datetime(y0.year, y0.month, y0.day)
    keys = list(d["series"])

    def rows() -> Any:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["time", "slot", *[f"{k}_kwh" if k.split(":")[0] != "soc" else k for k in keys]])
        yield buf.getvalue()
        for i, slot in enumerate(d["slots"]):
            buf.seek(0)
            buf.truncate()
            w.writerow(
                [(t0 + step * i).strftime("%Y-%m-%d %H:%M"), slot, *[str(d["series"][k][i]) for k in keys]]
            )
            yield buf.getvalue()

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="dispatch-{run_id[:8]}.csv"'},
    )


_TODAY_OWNER = "rules.body + load_profiles.series_kw"
_TODAY_KINDS: list[Any] = [
    "order",
    "regulation",
    "bill",
    "client_stated",
    "assumption",
    "derived",
    "measured",
]


def _sv_field() -> Any:
    return Field(default=None, json_schema_extra={"owner": _TODAY_OWNER, "ref_kinds": _TODAY_KINDS})


class TodayOut(BaseModel):
    """What the connection pays today for a year, for the Evaluate page's summary: the approved
    tariff applied to the load profile. Every figure is a SourcedValue carrying the tariff pages and
    the profile's provenance (invariant 1); the bills' own replay, line by line, is /replay."""

    source: str  # tariff
    annual: SourcedValue | None = _sv_field()  # INR for the year
    energy: SourcedValue | None = _sv_field()  # INR, the energy charges
    demand: SourcedValue | None = _sv_field()  # INR, the demand charges
    kwh: SourcedValue | None = _sv_field()  # the profile's energy for the year
    average_inr_per_kwh: SourcedValue | None = _sv_field()
    months: int
    note: str
    gaps: list[str] = []


@router.get("/connections/{connection_id}/today", response_model=TodayOut)
def today(
    connection_id: str,
    who: Annotated[Caller, Depends(caller)],
    as_of: Annotated[date | None, Query()] = None,
) -> TodayOut:
    """What the year costs today: the approved tariff's energy and demand charges applied to the
    connection's load profile (the bills' own replay, line by line, is /connections/{id}/replay)."""
    from . import cost as cost_router

    card = cost_router.connection_avoided_cost(connection_id, None, as_of)
    energy_lines = [x for x in card.annual if x.label == avoided_cost.ENERGY_YEAR]
    demand_lines = [x for x in card.annual if x.label == avoided_cost.DEMAND_YEAR]
    energy = sum((Decimal(x.value) for x in energy_lines), Decimal(0))
    demand = sum((Decimal(x.value) for x in demand_lines), Decimal(0))
    profile: SourcedValue | None = None
    with session_scope() as s:
        lp = s.scalars(
            select(LoadProfile)
            .where(LoadProfile.connection_id == connection_id)
            .order_by(LoadProfile.version.desc())
        ).first()
        if lp is not None:
            from ...intake import profile_synthesis

            kind = RefKind.MEASURED if lp.provenance == "measured" else RefKind.DERIVED
            profile = SourcedValue(
                value=(sum(profile_synthesis.decode(lp.series_kw), Decimal(0)) * Decimal("0.25")).quantize(
                    Decimal("1")
                ),
                unit=Unit.KWH,
                label="Consumption for the year",
                source_refs=(SourceRef(kind=kind, note=f"load profile v{lp.version} ({lp.provenance})"),),
            )
    lines = energy_lines + demand_lines
    total = energy + demand
    kwh = profile.value if profile is not None else Decimal(0)

    def money(v: Decimal, label: str) -> SourcedValue | None:
        return derive(v.quantize(Decimal("1")), Unit.INR, lines, label=label) if lines else None

    return TodayOut(
        source="tariff",
        annual=money(total, "Grid cost today, for the year"),
        energy=money(energy, "Energy charges, for the year"),
        demand=money(demand, "Demand charges, for the year"),
        kwh=profile,
        average_inr_per_kwh=(
            derive(
                (total / kwh).quantize(Decimal("0.01")),
                Unit.INR_PER_KWH,
                [*lines, profile],
                label="Average cost per unit today",
            )
            if lines and profile is not None and kwh
            else None
        ),
        months=12,
        note="the approved tariff applied to the year's load profile (energy and demand charges); "
        + ("; ".join(card.gaps.values()) if card.gaps else "every component sourced"),
        gaps=list(card.gaps.values()),
    )
