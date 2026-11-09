"""Scenarios and runs (journey step 5): an analyst defines what to size; a run solves it on the worker,
re-settles it (invariant 6) and stores it with its pins (invariant 5). Clients read finished runs;
a run that failed re-settlement is never shown to a client."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import select

from ...core.sourced import RefKind, SourcedValue, SourceRef
from ...db.base import session_scope
from ...db.models import Connection, Run, RunResult, Scenario, Site
from ...optimizer.scenarios import ScenarioSpec
from .. import runs as svc
from ..auth import Caller, analyst, caller

router = APIRouter(tags=["scenarios and runs"])

OWNER = "run_results.summary"
KINDS: list[JsonValue] = [
    "order",
    "regulation",
    "bill",
    "client_stated",
    "assumption",
    "derived",
    "market",
    "measured",
]


def _f(owner: str = OWNER, kinds: list[JsonValue] = KINDS) -> Any:
    return Field(json_schema_extra={"owner": owner, "ref_kinds": kinds})


def _o(owner: str = OWNER, kinds: list[JsonValue] = KINDS) -> Any:
    return Field(default=None, json_schema_extra={"owner": owner, "ref_kinds": kinds})


class ScenarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str
    name: str = Field(min_length=1, max_length=80)
    spec: ScenarioSpec


class ExchangeOut(BaseModel):
    """An exchange purchase: the consumer buys block by block at the clearing price (never sells)."""

    segment: str
    blocks_bought: int
    hours_bought: str
    avg_landed: SourcedValue = _f()
    share_of_load: SourcedValue = _f()


class LifecycleYearOut(BaseModel):
    year: int
    bau: str
    grid: str
    contracted: str
    om: str
    capex: str
    saving: str
    cash: str
    cumulative: str
    pv_cash: str


class LifecycleOut(BaseModel):
    """The settled year projected over the analysis period (engine.lifecycle)."""

    analysis_years: SourcedValue = _f()
    assumptions: dict[str, SourcedValue] = Field(
        json_schema_extra={"owner": "run_results.summary", "ref_kinds": ["assumption", "client_stated"]}
    )
    capex: SourcedValue | None = _o()
    pv_bau: SourcedValue | None = _o()
    pv_plan: SourcedValue | None = _o()
    npv: SourcedValue | None = _o()
    nominal_saving: SourcedValue | None = _o()
    simple_payback_years: SourcedValue | None = _o()
    discounted_payback_years: SourcedValue | None = _o()
    irr_pct: SourcedValue | None = _o()
    years: list[LifecycleYearOut]
    notes: list[str]


class MonthMixOut(BaseModel):
    month: date
    load_kwh: SourcedValue = _f()
    grid_kwh: SourcedValue = _f()
    withdrawn_kwh: SourcedValue = _f()
    sources: dict[str, SourcedValue] = Field(
        default_factory=dict, json_schema_extra={"owner": "run_results.summary", "ref_kinds": KINDS}
    )


class SizeOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    kind: str
    label: str
    kw: SourcedValue = _f()
    kwh: SourcedValue | None = _o()
    delivered_kwh: SourcedValue | None = _o()
    setoff_kwh: SourcedValue | None = _o()
    energy_cost: SourcedValue | None = _o()
    banked_kwh: SourcedValue | None = _o()
    unbanked_kwh: SourcedValue | None = _o()
    waterfall: dict[str, list[SourcedValue]] = Field(
        default_factory=dict, json_schema_extra={"owner": "rules.body + scenarios.spec", "ref_kinds": KINDS}
    )
    gaps: list[str] = Field(default_factory=list)
    ownership: str | None = None
    exchange: ExchangeOut | None = None


class AnnualOut(BaseModel):
    before: SourcedValue = _f()
    after: SourcedValue = _f()
    saving: SourcedValue = _f()
    capex: SourcedValue = _f()


class EmissionsOut(BaseModel):
    factor: SourcedValue = _f("scenarios.spec", ["client_stated", "assumption"])
    before_t: SourcedValue = _f()
    after_t: SourcedValue = _f()
    exchange_grid_kwh: SourcedValue | None = _o()  # exchange energy counted at the grid factor


class SettlementOut(BaseModel):
    grid_kwh: SourcedValue = _f()
    lapsed_kwh: SourcedValue = _f()
    withdrawn_kwh: SourcedValue = _f()
    rule: str | None


class BindingOut(BaseModel):
    name: str
    words: str
    refs: list[SourcedValue] = _f("rules.body + scenarios.spec")


class SensitivityOut(BaseModel):
    label: str
    saving: SourcedValue = _f()


class ProvenanceOut(BaseModel):
    load_profile: str
    prices: list[str]
    profile_ref: SourcedValue = _f("load_profiles.series_kw", ["measured", "derived"])


class SummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sizes: list[SizeOut]
    annual: AnnualOut
    payback_years: SourcedValue | None = _o()
    irr_pct: SourcedValue | None = _o()
    emissions: EmissionsOut
    settlement: SettlementOut
    contract_demand_kva: SourcedValue = _f()
    binding: list[BindingOut]
    provenance: ProvenanceOut
    sensitivities: list[SensitivityOut]
    notes: list[str]
    monthly: list[MonthMixOut] = Field(default_factory=list)
    lifecycle: LifecycleOut | None = None


class RunOut(BaseModel):
    id: str
    scenario_id: str
    status: str
    resolution_min: int
    created_at: datetime
    finished_at: datetime | None
    error: str | None
    replay_of: str | None
    pins: dict[str, Any]
    solver: dict[str, Any]
    summary: SummaryOut | None
    analyst: dict[str, Any] | None = None  # re-settlement check and cost lines (analyst only)
    identical_to_original: bool | None = None


class ScenarioOut(BaseModel):
    id: str
    site_id: str
    connection_id: str
    name: str
    spec: ScenarioSpec
    created_at: datetime
    latest_run: RunOut | None


class DispatchOut(BaseModel):
    run_id: str
    start: date
    minutes: int
    times: list[str]
    slots: list[str]
    series: dict[str, list[SourcedValue]] = Field(
        json_schema_extra={"owner": "run_results.dispatch", "ref_kinds": ["derived"]}
    )


def _run_out(s: Any, run: Run, who: Caller) -> RunOut:
    rr = s.get(RunResult, run.id)
    show = run.status == "done" or who.role == "analyst"
    identical = None
    if run.replay_of and rr is not None:
        orig = s.get(RunResult, run.replay_of)
        identical = orig is not None and orig.digest == rr.digest
    return RunOut(
        id=run.id,
        scenario_id=run.scenario_id,
        status=run.status,
        resolution_min=run.resolution_min,
        created_at=run.created_at,
        finished_at=run.finished_at,
        error=run.error if who.role == "analyst" else None,
        replay_of=run.replay_of,
        pins=run.pins or {},
        solver=run.solver or {},
        summary=SummaryOut.model_validate(rr.summary) if rr is not None and show else None,
        analyst=(
            {
                "resettle": rr.resettle,
                "lines_before": rr.summary.get("lines_before"),
                "lines_after": rr.summary.get("lines_after"),
            }
            if rr is not None and who.role == "analyst"
            else None
        ),
        identical_to_original=identical,
    )


def _visible(run: Run, who: Caller) -> None:
    if who.role != "analyst" and run.status != "done":
        raise HTTPException(404, "run not found")  # invariant 6: a client never sees an unsettled run


@router.post("/sites/{site_id}/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(site_id: str, body: ScenarioIn, who: Annotated[Caller, Depends(analyst)]) -> ScenarioOut:
    with session_scope(actor=who.actor, role=who.role) as s:
        if s.get(Site, site_id) is None:
            raise HTTPException(404, "site not found")
        conn = s.get(Connection, body.connection_id)
        if conn is None or conn.site_id != site_id:
            raise HTTPException(422, "the connection is not on this site")
        sc = Scenario(
            site_id=site_id,
            connection_id=conn.id,
            name=body.name,
            spec=body.spec.model_dump(mode="json"),
            created_by=who.actor,
        )
        s.add(sc)
        s.flush()
        s.refresh(sc)
        return ScenarioOut(
            id=sc.id,
            site_id=site_id,
            connection_id=conn.id,
            name=sc.name,
            spec=body.spec,
            created_at=sc.created_at,
            latest_run=None,
        )


@router.get("/sites/{site_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(site_id: str, who: Annotated[Caller, Depends(caller)]) -> list[ScenarioOut]:
    with session_scope() as s:
        out = []
        for sc in s.scalars(
            select(Scenario).where(Scenario.site_id == site_id).order_by(Scenario.created_at)
        ):
            q = select(Run).where(Run.scenario_id == sc.id, Run.replay_of.is_(None))
            if who.role != "analyst":
                q = q.where(Run.status == "done")
            run = s.scalars(q.order_by(Run.created_at.desc())).first()
            out.append(
                ScenarioOut(
                    id=sc.id,
                    site_id=sc.site_id,
                    connection_id=sc.connection_id,
                    name=sc.name,
                    spec=ScenarioSpec.model_validate(sc.spec),
                    created_at=sc.created_at,
                    latest_run=_run_out(s, run, who) if run else None,
                )
            )
        return out


@router.post("/scenarios/{scenario_id}/run", response_model=RunOut, status_code=202)
def run_scenario(
    scenario_id: str,
    who: Annotated[Caller, Depends(analyst)],
    wait: Annotated[bool, Query(description="solve in the request instead of on the worker")] = False,
) -> RunOut:
    with session_scope(actor=who.actor, role=who.role) as s:
        sc = s.get(Scenario, scenario_id)
        if sc is None:
            raise HTTPException(404, "scenario not found")
        run_id = svc.create_run(s, sc, who.actor).id
    if wait:
        svc.execute(run_id)
    with session_scope() as s:
        run = s.get(Run, run_id)
        assert run is not None
        return _run_out(s, run, who)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, who: Annotated[Caller, Depends(caller)]) -> RunOut:
    with session_scope() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        _visible(run, who)
        return _run_out(s, run, who)


@router.post("/runs/{run_id}/replay", response_model=RunOut, status_code=202)
def replay_run(
    run_id: str,
    who: Annotated[Caller, Depends(analyst)],
    wait: Annotated[bool, Query()] = False,
) -> RunOut:
    """Recompute a run from its pins (rule versions, load profile, price vintages, as-of date).
    `identical_to_original` says whether every result matches to the paisa."""
    with session_scope(actor=who.actor, role=who.role) as s:
        orig = s.get(Run, run_id)
        if orig is None:
            raise HTTPException(404, "run not found")
        if not orig.pins:
            raise HTTPException(409, "the run has not finished; nothing is pinned yet")
        sc = s.get(Scenario, orig.scenario_id)
        assert sc is not None
        new_id = svc.create_run(s, sc, who.actor, replay_of=orig).id
    if wait:
        svc.execute(new_id)
    with session_scope() as s:
        run = s.get(Run, new_id)
        assert run is not None
        return _run_out(s, run, who)


@router.get("/runs/{run_id}/dispatch", response_model=DispatchOut)
def run_dispatch(
    run_id: str,
    who: Annotated[Caller, Depends(caller)],
    start: Annotated[date | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
) -> DispatchOut:
    """The re-settled dispatch for a stretch of days (default: the week with the highest load)."""
    with session_scope() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        _visible(run, who)
        rr = s.get(RunResult, run_id)
        if rr is None:
            raise HTTPException(409, "the run has no result yet")
        d = svc.read_dispatch(rr.dispatch)
    y0 = date.fromisoformat(d["year_start"])
    per_day = 24 * 60 // int(d["minutes"])
    n = len(d["slots"])
    if start is None:
        load = [float(x) for x in d["series"]["load"]]
        weeks = [(sum(load[i : i + 7 * per_day]), i) for i in range(0, max(1, n - 7 * per_day), per_day)]
        i0 = max(weeks)[1] if weeks else 0
    else:
        i0 = (start - y0).days * per_day
        if not 0 <= i0 < n:
            raise HTTPException(422, "start is outside the run's year")
    i1 = min(n, i0 + days * per_day)
    ref = SourceRef(
        kind=RefKind.DERIVED, note=f"re-settled dispatch of run {run_id}; inputs in the run summary"
    )
    unit_of = {"soc": "kWh"}
    series = {}
    for k, vals in d["series"].items():
        series[k] = [
            SourcedValue(value=v, unit=unit_of.get(k.split(":")[0], "kWh"), source_refs=(ref,))
            for v in vals[i0:i1]
        ]
    step = timedelta(minutes=int(d["minutes"]))
    t0 = datetime(y0.year, y0.month, y0.day) + step * i0
    return DispatchOut(
        run_id=run_id,
        start=(y0 + timedelta(days=i0 // per_day)),
        minutes=int(d["minutes"]),
        times=[(t0 + step * j).strftime("%Y-%m-%dT%H:%M") for j in range(i1 - i0)],
        slots=d["slots"][i0:i1],
        series=series,
    )
