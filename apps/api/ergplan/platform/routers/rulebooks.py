"""Rulebook endpoints. Reading versions and rows is open to analysts; every write goes through
rulebook.service with the caller as the session's actor and role (the triggers check both)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ...db.base import session_scope
from ...db.models import Jurisdiction, Rule, RulebookVersion, RuleTest, RuleTestRun
from ...rulebook import golden, service
from ...rulebook.schemas import FAMILIES, UnknownFamily, family_schema
from ..auth import Caller, analyst

router = APIRouter(prefix="/rulebooks", tags=["rulebooks"])
Analyst = Annotated[Caller, Depends(analyst)]


class JurisdictionOut(BaseModel):
    id: str
    kind: str
    name: str
    state_code: str | None
    parent_id: str | None


class VersionOut(BaseModel):
    id: str
    family: str
    jurisdiction_id: str
    version: int
    status: str
    title: str | None
    effective_from: date
    effective_to: date | None
    origin: str
    golden_status: str
    created_by: str
    approved_by: str | None
    notes: str | None
    rows: int = 0

    @classmethod
    def of(cls, v: RulebookVersion, rows: int = 0) -> VersionOut:
        return cls(
            id=v.id,
            family=v.family,
            jurisdiction_id=v.jurisdiction_id,
            version=v.version,
            status=v.status,
            title=v.title,
            effective_from=v.effective_from,
            effective_to=v.effective_to,
            origin=v.origin,
            golden_status=v.golden_status,
            created_by=v.created_by,
            approved_by=v.approved_by,
            notes=v.notes,
            rows=rows,
        )


class RowOut(BaseModel):
    id: str
    position: int
    label: str | None
    scope: dict[str, Any]
    body: dict[str, Any]
    source_ref: dict[str, Any]
    field_refs: dict[str, Any]
    review: dict[str, Any]


class GoldenOut(BaseModel):
    name: str
    passed: bool | None
    given: dict[str, Any]
    expect: dict[str, Any]
    actual: dict[str, Any] | None
    source_ref: dict[str, Any] | None


class VersionDetail(BaseModel):
    version: VersionOut
    rows: list[RowOut]
    golden: list[GoldenOut]


class RowIn(BaseModel):
    label: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any]
    source_ref: dict[str, Any]
    field_refs: dict[str, Any] | None = None
    review: dict[str, Any] | None = None


class ProposeIn(BaseModel):
    family: str
    jurisdiction_id: str
    effective_from: date
    effective_to: date | None = None
    title: str | None = None
    notes: str | None = None
    rows: list[RowIn]


def _errors(e: Exception) -> HTTPException:
    if isinstance(e, service.InvalidRows):
        return HTTPException(422, {"message": "rows do not match the family schema", "errors": e.errors})
    if isinstance(e, service.NotADraft | service.ApprovalRefused):
        return HTTPException(409, str(e))
    if isinstance(e, service.UnknownJurisdiction | UnknownFamily | LookupError):
        return HTTPException(404, str(e))
    if isinstance(e, DBAPIError):
        return HTTPException(409, str(e.orig).split("\n")[0])
    raise e


def _detail(s: Session, vid: str) -> VersionDetail:
    v = s.get(RulebookVersion, vid)
    if v is None:
        raise HTTPException(404, "version not found")
    rows = list(s.scalars(select(Rule).where(Rule.rulebook_version_id == vid).order_by(Rule.position)))
    tests = list(
        s.scalars(
            select(RuleTest).where(RuleTest.jurisdiction_id == v.jurisdiction_id, RuleTest.family == v.family)
        )
    )
    runs = {
        r.test_id: r for r in s.scalars(select(RuleTestRun).where(RuleTestRun.rulebook_version_id == vid))
    }
    return VersionDetail(
        version=VersionOut.of(v, len(rows)),
        rows=[
            RowOut(
                id=r.id,
                position=r.position,
                label=r.label,
                scope=r.scope,
                body=r.body,
                source_ref=r.source_ref,
                field_refs=r.field_refs or {},
                review=r.review or {},
            )
            for r in rows
        ],
        golden=[
            GoldenOut(
                name=t.name,
                passed=runs[t.id].passed if t.id in runs else None,
                given=t.given,
                expect=t.expect,
                actual=runs[t.id].actual if t.id in runs else None,
                source_ref=t.source_ref,
            )
            for t in tests
        ],
    )


@router.get("/jurisdictions", response_model=list[JurisdictionOut])
def jurisdictions() -> list[JurisdictionOut]:
    with session_scope() as s:
        return [
            JurisdictionOut(id=j.id, kind=j.kind, name=j.name, state_code=j.state_code, parent_id=j.parent_id)
            for j in s.scalars(
                select(Jurisdiction).order_by(Jurisdiction.state_code, Jurisdiction.kind, Jurisdiction.id)
            )
        ]


class CoverageOut(BaseModel):
    state: str
    name: str
    families: dict[str, str]  # family → "approved" | "not yet sourced"
    jurisdictions: dict[
        str, list[str]
    ]  # family → the jurisdictions (DISCOM, group or state) with approved rows


@router.get("/coverage", response_model=list[CoverageOut])
def coverage(on: date | None = None) -> list[CoverageOut]:
    """Per state, which rule families are approved and in force (on a date, default today) and which
    are not yet sourced — the honest map of where a plan's numbers can come from."""
    when = on or date.today()
    with session_scope() as s:
        states = list(
            s.scalars(select(Jurisdiction).where(Jurisdiction.kind == "state").order_by(Jurisdiction.id))
        )
        by_state: dict[str, dict[str, set[str]]] = {st.id: {} for st in states}
        for v in s.scalars(select(RulebookVersion).where(RulebookVersion.status == "approved")):
            if v.effective_from > when or (v.effective_to is not None and v.effective_to < when):
                continue
            j = s.get(Jurisdiction, v.jurisdiction_id)
            code = j.state_code if j is not None else None
            if code in by_state:
                by_state[code].setdefault(v.family, set()).add(v.jurisdiction_id)
        out = []
        for st in states:
            fam = by_state[st.id]
            out.append(
                CoverageOut(
                    state=st.id,
                    name=st.name,
                    families={f: ("approved" if f in fam else "not yet sourced") for f in FAMILIES},
                    jurisdictions={f: sorted(v) for f, v in fam.items()},
                )
            )
        return out


@router.get("/families")
def families() -> dict[str, Any]:
    return {f: family_schema(f) for f in FAMILIES}


@router.get("/versions", response_model=list[VersionOut])
def versions(
    jurisdiction: str | None = None, family: str | None = None, status: str | None = None
) -> list[VersionOut]:
    with session_scope() as s:
        q = select(RulebookVersion).order_by(
            RulebookVersion.jurisdiction_id, RulebookVersion.family, RulebookVersion.version.desc()
        )
        if jurisdiction:
            q = q.where(RulebookVersion.jurisdiction_id == jurisdiction)
        if family:
            q = q.where(RulebookVersion.family == family)
        if status:
            q = q.where(RulebookVersion.status == status)
        out = []
        for v in s.scalars(q):
            n = len(list(s.scalars(select(Rule.id).where(Rule.rulebook_version_id == v.id))))
            out.append(VersionOut.of(v, n))
        return out


@router.get("/versions/{vid}", response_model=VersionDetail)
def version(vid: str) -> VersionDetail:
    with session_scope() as s:
        return _detail(s, vid)


@router.post("/versions", response_model=VersionDetail, status_code=201)
def propose(body: ProposeIn, who: Analyst) -> VersionDetail:
    try:
        with session_scope(actor=who.actor, role=who.role) as s:
            v = service.propose(
                s,
                family=body.family,
                jurisdiction_id=body.jurisdiction_id,
                rows=[r.model_dump(exclude_none=True) for r in body.rows],
                actor=who.actor,
                effective_from=body.effective_from,
                effective_to=body.effective_to,
                title=body.title,
                notes=body.notes,
            )
            return _detail(s, v.id)
    except Exception as e:
        raise _errors(e) from e


@router.put("/versions/{vid}/rows/{rid}", response_model=VersionDetail)
def update_row(vid: str, rid: str, row: RowIn, who: Analyst) -> VersionDetail:
    try:
        with session_scope(actor=who.actor, role=who.role) as s:
            service.update_row(s, vid, rid, row.model_dump(exclude_none=True))
            return _detail(s, vid)
    except Exception as e:
        raise _errors(e) from e


@router.delete("/versions/{vid}/rows/{rid}", response_model=VersionDetail)
def delete_row(vid: str, rid: str, who: Analyst) -> VersionDetail:
    try:
        with session_scope(actor=who.actor, role=who.role) as s:
            service.delete_row(s, vid, rid)
            return _detail(s, vid)
    except Exception as e:
        raise _errors(e) from e


@router.post("/versions/{vid}/duplicate", response_model=VersionDetail, status_code=201)
def duplicate(vid: str, who: Analyst) -> VersionDetail:
    try:
        with session_scope(actor=who.actor, role=who.role) as s:
            v = service.duplicate(s, vid, actor=who.actor)
            return _detail(s, v.id)
    except Exception as e:
        raise _errors(e) from e


@router.post("/versions/{vid}/golden", response_model=VersionDetail)
def run_golden(vid: str, who: Analyst) -> VersionDetail:
    try:
        with session_scope(actor=who.actor, role=who.role) as s:
            golden.sync_tests(s)
            service.run_golden(s, vid)
            return _detail(s, vid)
    except Exception as e:
        raise _errors(e) from e


@router.post("/versions/{vid}/approve", response_model=VersionDetail)
def approve(vid: str, who: Analyst) -> VersionDetail:
    try:
        with session_scope(actor=who.actor, role=who.role) as s:
            golden.sync_tests(s)
            service.approve(s, vid, actor=who.actor, role=who.role)
            return _detail(s, vid)
    except Exception as e:
        raise _errors(e) from e


@router.post("/versions/{vid}/reject", response_model=VersionDetail)
def reject(vid: str, who: Analyst) -> VersionDetail:
    try:
        with session_scope(actor=who.actor, role=who.role) as s:
            service.reject(s, vid)
            return _detail(s, vid)
    except Exception as e:
        raise _errors(e) from e
