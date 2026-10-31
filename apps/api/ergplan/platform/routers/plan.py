"""The live plan (journey step 6): build the standard plan for a connection with no analyst, share it
by token, read it logged out at /p/{token}, export it to PDF, ask what-if, read explanations."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.settings import get_settings
from ...core.sourced import SourcedValue
from ...db.base import session_scope
from ...db.models import Connection, Run, Scenario, SourceDocument
from ...optimizer.scenarios import standard
from ...providers.openai_client import ProviderError
from ...report import explain as explainer
from ...report import pdf as pdf_export
from ...report import plan as plan_data
from ...report import share
from ...report.whatif import WhatIf, WhatIfFailed, evaluate
from .. import runs as svc
from ..auth import Caller, caller
from .runs import KINDS, SummaryOut

router = APIRouter(tags=["live plan"])


class ScenarioPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario_id: str
    name: str
    run_id: str
    resolution_min: int
    finished_at: datetime | None
    summary: SummaryOut
    analyst: dict[str, Any] | None = None


class DocumentRef(BaseModel):
    id: str
    title: str
    regulator: str | None
    url_public: str | None
    url: str
    pages: list[int]


class Editable(BaseModel):
    tool: str
    source: str | None
    label: str
    value: SourcedValue = Field(json_schema_extra={"owner": "run_results.summary", "ref_kinds": KINDS})


class PlanOut(BaseModel):
    token: str | None = None
    connection_id: str
    client: str
    site: str
    state: str
    discom: str
    category: str | None
    voltage_kv: str | None
    profile: str | None
    scenarios: list[ScenarioPlan]
    recommended: str | None
    pending_runs: int
    documents: list[DocumentRef]
    assumptions: list[dict[str, Any]]
    editable: list[Editable]
    analyst_view: bool = False


class BuildOut(BaseModel):
    created: int
    queued: list[str]


class ShareOut(BaseModel):
    token: str
    path: str
    url: str


class WhatIfOut(BaseModel):
    described: str
    sentence: str
    resolution_min: int
    annual: dict[str, SourcedValue] = Field(
        json_schema_extra={"owner": "run_results.summary", "ref_kinds": KINDS}
    )
    base_saving: SourcedValue = Field(json_schema_extra={"owner": "run_results.summary", "ref_kinds": KINDS})


class ExplainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    item: str = Field(pattern=r"^(waterfall|binding):.{1,80}$")


class ExplainOut(BaseModel):
    kind: str = "explanation"
    text: str
    prompt: str
    cached: bool
    values: list[SourcedValue] = Field(json_schema_extra={"owner": "run_results.summary", "ref_kinds": KINDS})


@router.post("/connections/{connection_id}/plan", response_model=BuildOut, status_code=202)
def build_plan(
    connection_id: str,
    who: Annotated[Caller, Depends(caller)],
    as_of: Annotated[date | None, Query()] = None,
    resolution_min: Annotated[int, Query(ge=15, le=60, multiple_of=15)] = 15,
    wait: Annotated[bool, Query()] = False,
) -> BuildOut:
    """Size the three standard scenarios for a connection (no analyst needed). Scenarios that already
    exist are not duplicated; each gets a run unless one is queued, running or settled."""
    queued: list[str] = []
    created = 0
    with session_scope(actor=who.actor, role=who.role) as s:
        conn = s.get(Connection, connection_id)
        if conn is None:
            raise HTTPException(404, "connection not found")
        have = {sc.name: sc for sc in s.scalars(select(Scenario).where(Scenario.connection_id == conn.id))}
        if resolution_min not in (15, 60):
            raise HTTPException(422, "resolution is 15 or 60 minutes")
        for name, spec in standard(as_of or date.today(), resolution_min):
            sc = have.get(name)
            if sc is None:
                sc = Scenario(
                    site_id=conn.site_id,
                    connection_id=conn.id,
                    name=name,
                    spec=spec.model_dump(mode="json"),
                    created_by=who.actor,
                )
                s.add(sc)
                s.flush()
                created += 1
            busy = s.scalars(
                select(Run).where(Run.scenario_id == sc.id, Run.status.in_(("queued", "running", "done")))
            ).first()
            if busy is None:
                queued.append(svc.create_run(s, sc, who.actor).id)
    if wait:
        for rid in queued:
            svc.execute(rid)
    return BuildOut(created=created, queued=queued)


@router.post("/connections/{connection_id}/share", response_model=ShareOut, status_code=201)
def share_plan(connection_id: str, who: Annotated[Caller, Depends(caller)]) -> ShareOut:
    with session_scope(actor=who.actor) as s:
        try:
            link = share.create(s, connection_id, who.actor)
        except share.LinkNotFound as e:
            raise HTTPException(404, "connection not found") from e
        path = f"/p/{link.token}"
        return ShareOut(
            token=link.token, path=path, url=f"{get_settings().ergplan_public_url.rstrip('/')}{path}"
        )


@router.get("/connections/{connection_id}/plan", response_model=PlanOut)
def plan_for_connection(connection_id: str, who: Annotated[Caller, Depends(caller)]) -> PlanOut:
    with session_scope() as s:
        try:
            d = plan_data.build(s, connection_id, analyst=False)
        except plan_data.PlanNotFound as e:
            raise HTTPException(404, "connection not found") from e
    return PlanOut.model_validate(d)


def _resolve(s: Session, token: str) -> str:
    try:
        return share.resolve(s, token).connection_id
    except share.LinkNotFound as e:
        raise HTTPException(404, "this link does not exist or was withdrawn") from e


@router.get("/p/{token}", response_model=PlanOut)
def live_plan(
    token: str,
    who: Annotated[Caller, Depends(caller)],
    view: Annotated[str | None, Query(pattern="^(client|analyst)$")] = None,
) -> PlanOut:
    """The shared plan, logged out. `view=analyst` adds every assumption, rule version, run pin and
    margin — only for the analyst role (the jouleWise view)."""
    analyst = view == "analyst" and who.role == "analyst" and who.actor != "anonymous"
    if view == "analyst" and not analyst:
        raise HTTPException(403, "the jouleWise view is for analysts")
    with session_scope() as s:
        cid = _resolve(s, token)
        d = plan_data.build(s, cid, analyst=analyst)
    return PlanOut.model_validate({**d, "token": token, "analyst_view": analyst})


@router.get("/p/{token}/pdf")
def live_plan_pdf(token: str) -> Response:
    with session_scope() as s:
        _resolve(s, token)
    try:
        data = pdf_export.export(token)
    except pdf_export.PdfUnavailable as e:
        raise HTTPException(503, str(e)) from e
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="ergplan-{token[:8]}.pdf"'},
    )


def recommended_run(s: Session, connection_id: str) -> Run:
    d = plan_data.build(s, connection_id)
    rec = next((x for x in d["scenarios"] if x["scenario_id"] == d["recommended"]), None)
    if rec is None:
        raise HTTPException(409, "the plan has no settled scenario yet")
    run = s.get(Run, rec["run_id"])
    assert run is not None
    return run


@router.post("/p/{token}/whatif", response_model=WhatIfOut)
def live_whatif(token: str, body: WhatIf, scenario_id: Annotated[str | None, Query()] = None) -> WhatIfOut:
    with session_scope() as s:
        cid = _resolve(s, token)
        if scenario_id:
            run = next(
                (
                    s.get(Run, x["run_id"])
                    for x in plan_data.build(s, cid)["scenarios"]
                    if x["scenario_id"] == scenario_id
                ),
                None,
            )
            if run is None:
                raise HTTPException(404, "scenario not in this plan")
        else:
            run = recommended_run(s, cid)
        try:
            out = evaluate(s, run, body)
        except WhatIfFailed as e:
            raise HTTPException(422, str(e)) from e
    return WhatIfOut.model_validate(out)


@router.post("/p/{token}/explain", response_model=ExplainOut)
def live_explain(token: str, body: ExplainIn) -> ExplainOut:
    with session_scope(actor="explanations") as s:
        cid = _resolve(s, token)
        d = plan_data.build(s, cid)
        sc = next((x for x in d["scenarios"] if x["scenario_id"] == body.scenario_id), None)
        if sc is None:
            raise HTTPException(404, "scenario not in this plan")
        kind, key = body.item.split(":", 1)
        summ = sc["summary"]
        if kind == "waterfall":
            z = next((x for x in summ["sizes"] if x["id"] == key), None)
            slots = list((z or {}).get("waterfall", {}).items())
            if z is None or not slots:
                raise HTTPException(404, "no waterfall for that source")
            title, values = f"{z['label']}: landed cost at the meter, {slots[0][0]}", slots[0][1]
        else:
            b = next((x for x in summ["binding"] if x["name"] == key), None)
            if b is None:
                raise HTTPException(404, "no such binding constraint")
            title, values = b["words"], b["refs"]
        titles = {
            doc.id: doc.title
            for doc in s.scalars(
                select(SourceDocument).where(SourceDocument.id.in_([x["id"] for x in d["documents"]]))
            )
        }
        try:
            out = explainer.explain(s, title, values, titles)
        except ProviderError as e:
            raise HTTPException(503, f"explanation unavailable: {e}") from e
    return ExplainOut(text=out["text"], prompt=out["prompt"], cached=out["cached"], values=values)
