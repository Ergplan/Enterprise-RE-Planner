"""The audit of a plan: the chain from the generator's price to the saving, link by link, each with its
rate, its rule and the page it rests on; the client's own workings set against it; the audit chat;
proposed rule changes for analysts. The client sees and works on their own connection; an analyst on
any, and decides proposals."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.base import session_scope
from ...db.models import AuditMessage, Connection, RuleProposal, Working, WorkingLine
from ...providers import openai_client
from ...report import audit, audit_chat
from ...report import chain as chain_data
from ..auth import Caller, analyst, caller, owned_connection

router = APIRouter(tags=["audit"])


class LineOut(BaseModel):
    id: str
    working_id: str
    chain_key: str | None
    compare: str
    label: str
    value: str  # as written
    scale: str
    unit: str
    page: int
    quote: str
    theirs: str | None  # in our unit
    ours: str | None
    ours_unit: str | None
    difference: str | None
    status: str
    note: str | None
    kind: str | None  # yours | regulatory | computed (of the link)
    created_by: str
    created_at: datetime


class WorkingOut(BaseModel):
    id: str
    connection_id: str
    filename: str
    pages: list[dict[str, Any]]  # [{page, name}]
    uploaded_by: str
    created_at: datetime
    lines: list[LineOut]


class ProposalOut(BaseModel):
    id: str
    connection_id: str
    working_line_id: str | None
    rule_id: str
    family: str
    jurisdiction_id: str
    rule_label: str | None
    pointer: str
    current: str | None
    proposed: str
    unit: str
    reason: str
    status: str
    proposed_by: str
    created_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    draft_version_id: str | None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    data: dict[str, Any]
    actor: str
    created_at: datetime


class AuditOut(BaseModel):
    workings: list[WorkingOut]
    messages: list[MessageOut]
    proposals: list[ProposalOut]


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    scenario_id: str | None = Field(default=None, max_length=64)


class ChatOut(BaseModel):
    reply: str
    tool_results: list[dict[str, Any]]


class OwnershipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(max_length=64)
    ownership: Literal["captive", "group_captive", "third_party"]
    scenario_id: str | None = Field(default=None, max_length=64)


class ProposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=800)
    scenario_id: str | None = Field(default=None, max_length=64)


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=800)


class AcceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(max_length=64)
    page: int = Field(ge=1)
    quote: str = Field(min_length=8, max_length=400)
    note: str | None = Field(default=None, max_length=800)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=3, max_length=800)


class RerunOut(BaseModel):
    scenario_id: str
    scenario: str
    run_id: str
    status: str


def _s(d: Decimal | None) -> str | None:
    return None if d is None else format(d.normalize(), "f")


def _line_out(line: WorkingLine, steps: dict[str, chain_data.ChainStep]) -> LineOut:
    step = steps.get(line.chain_key) if line.chain_key else None
    return LineOut(
        id=line.id,
        working_id=line.working_id,
        chain_key=line.chain_key,
        compare=line.compare,
        label=line.label,
        value=_s(line.value) or "",
        scale=line.scale,
        unit=line.unit,
        page=line.page,
        quote=line.quote,
        theirs=_s(line.theirs),
        ours=_s(line.ours),
        ours_unit=line.ours_unit,
        difference=_s(line.theirs - line.ours) if line.theirs is not None and line.ours is not None else None,
        status=line.status,
        note=line.note,
        kind=audit.what_kind(step) if step else None,
        created_by=line.created_by,
        created_at=line.created_at,
    )


def _proposal_out(p: RuleProposal) -> ProposalOut:
    return ProposalOut(
        id=p.id,
        connection_id=p.connection_id,
        working_line_id=p.working_line_id,
        rule_id=p.rule_id,
        family=p.family,
        jurisdiction_id=p.jurisdiction_id,
        rule_label=p.rule_label,
        pointer=p.pointer,
        current=_s(p.current),
        proposed=_s(p.proposed) or "",
        unit=p.unit,
        reason=p.reason,
        status=p.status,
        proposed_by=p.proposed_by,
        created_at=p.created_at,
        decided_by=p.decided_by,
        decided_at=p.decided_at,
        decision_note=p.decision_note,
        draft_version_id=p.draft_version_id,
    )


def _working_out(s: Session, w: Working, steps: dict[str, chain_data.ChainStep]) -> WorkingOut:
    lines = s.scalars(
        select(WorkingLine).where(WorkingLine.working_id == w.id).order_by(WorkingLine.created_at)
    )
    return WorkingOut(
        id=w.id,
        connection_id=w.connection_id,
        filename=w.filename,
        pages=[{"page": p["page"], "name": p["name"]} for p in w.pages],
        uploaded_by=w.uploaded_by,
        created_at=w.created_at,
        lines=[_line_out(x, steps) for x in lines],
    )


def _chain(s: Session, connection_id: str, scenario_id: str | None) -> chain_data.Chain:
    try:
        return chain_data.build(s, connection_id, scenario_id)
    except chain_data.ChainNotFound as e:
        raise HTTPException(404, f"no settled plan to audit: {e}") from e


def _steps(s: Session, connection_id: str, scenario_id: str | None) -> dict[str, chain_data.ChainStep]:
    try:
        return chain_data.steps_by_key(chain_data.build(s, connection_id, scenario_id))
    except chain_data.ChainNotFound:
        return {}


def _bad(e: audit.AuditError) -> HTTPException:
    return HTTPException(422, str(e))


def _line_conn(s: Session, who: Caller, line_id: str) -> str:
    line = s.get(WorkingLine, line_id)
    w = s.get(Working, line.working_id) if line else None
    if line is None or w is None:
        raise HTTPException(404, "line not found")
    owned_connection(s, who, w.connection_id)
    return w.connection_id


def _rerun(s: Session, sc_id: str, sc_name: str, run_id: str) -> RerunOut:
    return RerunOut(scenario_id=sc_id, scenario=sc_name, run_id=run_id, status="queued")


# ---------------------------------------------------------------- the chain


@router.get("/connections/{connection_id}/chain", response_model=chain_data.Chain)
def get_chain(
    connection_id: str,
    who: Annotated[Caller, Depends(caller)],
    scenario_id: Annotated[str | None, Query(max_length=64)] = None,
) -> chain_data.Chain:
    with session_scope(actor=who.actor) as s:
        owned_connection(s, who, connection_id)
        return _chain(s, connection_id, scenario_id)


@router.get("/connections/{connection_id}/audit", response_model=AuditOut)
def get_audit(
    connection_id: str,
    who: Annotated[Caller, Depends(caller)],
    scenario_id: Annotated[str | None, Query(max_length=64)] = None,
) -> AuditOut:
    """The connection's workings with their lines, the audit chat so far and its proposals."""
    with session_scope(actor=who.actor) as s:
        owned_connection(s, who, connection_id)
        steps = _steps(s, connection_id, scenario_id)
        workings = s.scalars(
            select(Working).where(Working.connection_id == connection_id).order_by(Working.created_at)
        )
        messages = s.scalars(
            select(AuditMessage)
            .where(AuditMessage.connection_id == connection_id)
            .order_by(AuditMessage.created_at)
        )
        proposals = s.scalars(
            select(RuleProposal)
            .where(RuleProposal.connection_id == connection_id)
            .order_by(RuleProposal.created_at)
        )
        return AuditOut(
            workings=[_working_out(s, w, steps) for w in workings],
            messages=[
                MessageOut(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    data=m.data,
                    actor=m.actor,
                    created_at=m.created_at,
                )
                for m in messages
            ],
            proposals=[_proposal_out(p) for p in proposals],
        )


# ---------------------------------------------------------------- workings and lines


@router.post("/connections/{connection_id}/workings", response_model=WorkingOut, status_code=201)
async def upload_working(
    connection_id: str,
    who: Annotated[Caller, Depends(caller)],
    file: Annotated[UploadFile, File()],
    scenario_id: Annotated[str | None, Form(max_length=64)] = None,
) -> WorkingOut:
    data = await file.read(audit.MAX_BYTES + 1)
    with session_scope(actor=who.actor) as s:
        owned_connection(s, who, connection_id)
        if s.get(Connection, connection_id) is None:
            raise HTTPException(404, "connection not found")
        try:
            w = audit.store_working(
                s,
                connection_id,
                file.filename or "working.txt",
                file.content_type or "application/octet-stream",
                data,
                who.actor,
                scenario_id,
            )
        except audit.AuditError as e:
            raise _bad(e) from e
        s.add(
            AuditMessage(
                connection_id=connection_id,
                role="action",
                content=f"Working uploaded: {w.filename} ({len(w.pages)} pages or sheets).",
                data={"working_id": w.id},
                actor=who.actor,
            )
        )
        return _working_out(s, w, _steps(s, connection_id, scenario_id))


@router.get("/workings/{working_id}/file")
def working_file(working_id: str, who: Annotated[Caller, Depends(caller)]) -> FileResponse:
    with session_scope(actor=who.actor) as s:
        w = s.get(Working, working_id)
        if w is None:
            raise HTTPException(404, "working not found")
        owned_connection(s, who, w.connection_id)
        path, name, ctype = Path(w.path), w.filename, w.content_type
    if not path.exists():
        raise HTTPException(404, "the file is no longer stored")
    return FileResponse(path, media_type=ctype, filename=name)


@router.post("/workings/{working_id}/lines", response_model=LineOut, status_code=201)
def add_line(
    working_id: str,
    body: audit.LineIn,
    who: Annotated[Caller, Depends(caller)],
    scenario_id: Annotated[str | None, Query(max_length=64)] = None,
) -> LineOut:
    """A figure set against a link by hand (the same checks as the assistant's)."""
    with session_scope(actor=who.actor) as s:
        w = s.get(Working, working_id)
        if w is None:
            raise HTTPException(404, "working not found")
        owned_connection(s, who, w.connection_id)
        chain = _chain(s, w.connection_id, scenario_id)
        try:
            line = audit.record_line(s, w, chain, body, who.actor)
        except audit.AuditError as e:
            raise _bad(e) from e
        return _line_out(line, chain_data.steps_by_key(chain))


@router.post("/working-lines/{line_id}/use", response_model=RerunOut, status_code=202)
def use_line(
    line_id: str,
    who: Annotated[Caller, Depends(caller)],
    scenario_id: Annotated[str | None, Query(max_length=64)] = None,
) -> RerunOut:
    with session_scope(actor=who.actor) as s:
        conn = _line_conn(s, who, line_id)
        try:
            sc, run_id = audit.use_their_figure(s, conn, _chain(s, conn, scenario_id), line_id, who.actor)
        except audit.AuditError as e:
            raise _bad(e) from e
        return _rerun(s, sc.id, sc.name, run_id)


@router.post("/working-lines/{line_id}/accept-ours", response_model=LineOut)
def accept_ours(line_id: str, body: NoteIn, who: Annotated[Caller, Depends(caller)]) -> LineOut:
    with session_scope(actor=who.actor) as s:
        conn = _line_conn(s, who, line_id)
        line = audit.accept_ours(s, conn, line_id, body.note)
        return _line_out(line, _steps(s, conn, None))


@router.post("/working-lines/{line_id}/propose", response_model=ProposalOut, status_code=201)
def propose(line_id: str, body: ProposeIn, who: Annotated[Caller, Depends(caller)]) -> ProposalOut:
    with session_scope(actor=who.actor) as s:
        conn = _line_conn(s, who, line_id)
        try:
            p = audit.propose_rule_change(
                s, conn, _chain(s, conn, body.scenario_id), line_id, body.reason, who.actor
            )
        except audit.AuditError as e:
            raise _bad(e) from e
        return _proposal_out(p)


@router.post("/connections/{connection_id}/ownership", response_model=RerunOut, status_code=202)
def set_ownership(connection_id: str, body: OwnershipIn, who: Annotated[Caller, Depends(caller)]) -> RerunOut:
    with session_scope(actor=who.actor) as s:
        owned_connection(s, who, connection_id)
        try:
            sc, run_id = audit.set_ownership(
                s,
                connection_id,
                _chain(s, connection_id, body.scenario_id),
                body.source_id,
                body.ownership,
                who.actor,
            )
        except audit.AuditError as e:
            raise _bad(e) from e
        return _rerun(s, sc.id, sc.name, run_id)


@router.post("/connections/{connection_id}/audit/refresh")
def refresh(
    connection_id: str,
    who: Annotated[Caller, Depends(caller)],
    scenario_id: Annotated[str | None, Query(max_length=64)] = None,
) -> dict[str, int]:
    """Compare the open lines again with the latest settled chain (after a run with their figures)."""
    with session_scope(actor=who.actor) as s:
        owned_connection(s, who, connection_id)
        return {"compared": audit.refresh_lines(s, connection_id, _chain(s, connection_id, scenario_id))}


# ---------------------------------------------------------------- the chat


@router.post("/connections/{connection_id}/audit/chat", response_model=ChatOut)
def chat(connection_id: str, body: ChatIn, who: Annotated[Caller, Depends(caller)]) -> ChatOut:
    with session_scope(actor=who.actor) as s:
        owned_connection(s, who, connection_id)
        _chain(s, connection_id, body.scenario_id)  # 404 before any model call
        try:
            reply, results = audit_chat.converse(s, connection_id, body.scenario_id, body.message, who.actor)
        except openai_client.NoModelConfigured as e:
            raise HTTPException(503, "the audit assistant is not configured on this server") from e
        except openai_client.ProviderError as e:
            raise HTTPException(502, str(e)) from e
        return ChatOut(reply=reply, tool_results=results)


# ---------------------------------------------------------------- proposals (analysts decide)


@router.get("/rule-proposals", response_model=list[ProposalOut])
def list_proposals(
    who: Annotated[Caller, Depends(analyst)],
    status: Annotated[Literal["open", "accepted", "rejected"] | None, Query()] = "open",
) -> list[ProposalOut]:
    with session_scope() as s:
        q = select(RuleProposal).order_by(RuleProposal.created_at)
        if status:
            q = q.where(RuleProposal.status == status)
        return [_proposal_out(p) for p in s.scalars(q)]


@router.post("/rule-proposals/{proposal_id}/accept", response_model=ProposalOut)
def accept_proposal(
    proposal_id: str, body: AcceptIn, who: Annotated[Caller, Depends(analyst)]
) -> ProposalOut:
    """A new draft version of the rule's rulebook with the field changed, cited to the regulation."""
    with session_scope(actor=who.actor, role=who.role) as s:
        try:
            p = audit.accept_proposal(
                s, proposal_id, who.actor, body.document_id, body.page, body.quote, body.note
            )
        except audit.AuditError as e:
            raise _bad(e) from e
        return _proposal_out(p)


@router.post("/rule-proposals/{proposal_id}/reject", response_model=ProposalOut)
def reject_proposal(
    proposal_id: str, body: RejectIn, who: Annotated[Caller, Depends(analyst)]
) -> ProposalOut:
    with session_scope(actor=who.actor, role=who.role) as s:
        try:
            return _proposal_out(audit.reject_proposal(s, proposal_id, who.actor, body.note))
        except audit.AuditError as e:
            raise _bad(e) from e
