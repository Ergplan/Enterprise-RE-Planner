"""The single writer of rulebook_versions and rules (invariant 3). Every function takes a session
opened with `session_scope(actor=..., role=...)`; the database triggers audit each write and
refuse an approval without the analyst role and green golden tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..db.models import Jurisdiction, Rule, RulebookVersion
from . import golden
from .schemas import FAMILIES, UnknownFamily, validate_row


class InvalidRows(ValueError):
    def __init__(self, errors: dict[int, list[str]]):
        self.errors = errors
        super().__init__("; ".join(f"row {i}: {', '.join(e)}" for i, e in errors.items()))


class NotADraft(ValueError):
    pass


class ApprovalRefused(PermissionError):
    pass


class UnknownJurisdiction(LookupError):
    pass


ROW_KEYS = ("scope", "body", "source_ref", "field_refs", "label", "position")


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row[k] for k in ROW_KEYS if k in row and row[k] is not None}
    if not out.get("field_refs"):
        out.pop("field_refs", None)
    return out


def validate_rows(family: str, rows: list[dict[str, Any]]) -> dict[int, list[str]]:
    if family not in FAMILIES:
        raise UnknownFamily(family)
    errors = {}
    for i, row in enumerate(rows):
        e = validate_row(family, _clean_row(row))
        if e:
            errors[i] = e
    return errors


# ---------------------------------------------------------------- jurisdictions


def sync_jurisdictions(session: Session, path: Path | None = None) -> int:
    """Upsert packages/rulebooks/jurisdictions.yaml. Idempotent."""
    data = yaml.safe_load((path or get_settings().rulebooks_dir / "jurisdictions.yaml").read_text())
    rows: list[tuple[str, str, str, str | None, str | None]] = []
    for r in data.get("regulators", []):
        rows.append((r["id"], "regulator", r["name"], r.get("state"), None))
    for r in data.get("states", []):
        rows.append((r["id"], "state", r["name"], r["id"], None))
    for r in data.get("groups", []):
        rows.append((r["id"], "group", r["name"], r["state"], r["state"]))
    for r in data.get("discoms", []):
        rows.append((r["id"], "discom", r["name"], r["state"], r.get("parent") or r["state"]))
    for jid, kind, name, state, parent in rows:
        j = session.get(Jurisdiction, jid) or Jurisdiction(id=jid)
        j.kind, j.name, j.state_code, j.parent_id = kind, name, state, parent
        session.add(j)
    session.flush()
    return len(rows)


def jurisdiction_chain(session: Session, jurisdiction_id: str) -> list[str]:
    """The jurisdiction, then its parents up to the state, then CERC (central rules apply everywhere)."""
    chain: list[str] = []
    jid: str | None = jurisdiction_id
    while jid and jid not in chain:
        j = session.get(Jurisdiction, jid)
        if j is None:
            if not chain:
                raise UnknownJurisdiction(jurisdiction_id)
            break
        chain.append(j.id)
        jid = j.parent_id
    if "CERC" not in chain:
        chain.append("CERC")
    return chain


# ---------------------------------------------------------------- versions


def _next_version(session: Session, family: str, jurisdiction_id: str) -> int:
    n = session.scalar(
        select(func.max(RulebookVersion.version)).where(
            RulebookVersion.family == family, RulebookVersion.jurisdiction_id == jurisdiction_id
        )
    )
    return int(n or 0) + 1


def propose(
    session: Session,
    *,
    family: str,
    jurisdiction_id: str,
    rows: list[dict[str, Any]],
    actor: str,
    effective_from: date,
    effective_to: date | None = None,
    title: str | None = None,
    origin: str = "manual",
    notes: str | None = None,
) -> RulebookVersion:
    """A new draft version with these rows. Every row must validate against its family schema."""
    if session.get(Jurisdiction, jurisdiction_id) is None:
        raise UnknownJurisdiction(jurisdiction_id)
    errors = validate_rows(family, rows)
    if errors:
        raise InvalidRows(errors)
    v = RulebookVersion(
        family=family,
        jurisdiction_id=jurisdiction_id,
        version=_next_version(session, family, jurisdiction_id),
        status="draft",
        effective_from=effective_from,
        effective_to=effective_to,
        title=title,
        origin=origin,
        created_by=actor,
        notes=notes,
    )
    session.add(v)
    session.flush()
    _write_rows(session, v, rows)
    return v


def _write_rows(session: Session, v: RulebookVersion, rows: list[dict[str, Any]]) -> None:
    for i, row in enumerate(rows):
        r = _clean_row(row)
        session.add(
            Rule(
                rulebook_version_id=v.id,
                family=v.family,
                position=r.get("position", i),
                label=r.get("label"),
                scope=r.get("scope", {}),
                body=r["body"],
                source_ref=r["source_ref"],
                field_refs=r.get("field_refs", {}),
                review=row.get("review") or {},
            )
        )
    session.flush()


def _draft(session: Session, version_id: str) -> RulebookVersion:
    v = session.get(RulebookVersion, version_id)
    if v is None:
        raise LookupError(version_id)
    if v.status != "draft":
        raise NotADraft(f"version {v.version} of {v.family}/{v.jurisdiction_id} is {v.status}")
    return v


def revise(session: Session, version_id: str, rows: list[dict[str, Any]]) -> RulebookVersion:
    """Replace every row of a draft."""
    v = _draft(session, version_id)
    errors = validate_rows(v.family, rows)
    if errors:
        raise InvalidRows(errors)
    for r in session.scalars(select(Rule).where(Rule.rulebook_version_id == v.id)):
        session.delete(r)
    session.flush()
    _write_rows(session, v, rows)
    v.golden_status = "not_run"
    return v


def update_row(session: Session, version_id: str, rule_id: str, row: dict[str, Any]) -> Rule:
    v = _draft(session, version_id)
    errors = validate_rows(v.family, [row])
    if errors:
        raise InvalidRows(errors)
    r = session.get(Rule, rule_id)
    if r is None or r.rulebook_version_id != v.id:
        raise LookupError(rule_id)
    c = _clean_row(row)
    r.scope, r.body, r.source_ref = c.get("scope", {}), c["body"], c["source_ref"]
    r.field_refs, r.label = c.get("field_refs", {}), c.get("label")
    r.review = {**(r.review or {}), **(row.get("review") or {})}
    v.golden_status = "not_run"
    session.flush()
    return r


def delete_row(session: Session, version_id: str, rule_id: str) -> None:
    v = _draft(session, version_id)
    r = session.get(Rule, rule_id)
    if r is None or r.rulebook_version_id != v.id:
        raise LookupError(rule_id)
    session.delete(r)
    v.golden_status = "not_run"
    session.flush()


def duplicate(session: Session, version_id: str, actor: str) -> RulebookVersion:
    """A new draft carrying the rows of any version: the way to change an approved rulebook."""
    src = session.get(RulebookVersion, version_id)
    if src is None:
        raise LookupError(version_id)
    rows = [
        {
            "scope": r.scope,
            "body": r.body,
            "source_ref": r.source_ref,
            "field_refs": r.field_refs,
            "label": r.label,
            "position": r.position,
        }
        for r in session.scalars(
            select(Rule).where(Rule.rulebook_version_id == src.id).order_by(Rule.position)
        )
    ]
    return propose(
        session,
        family=src.family,
        jurisdiction_id=src.jurisdiction_id,
        rows=rows,
        actor=actor,
        effective_from=src.effective_from,
        effective_to=src.effective_to,
        title=src.title,
        origin="duplicate",
        notes=f"duplicated from version {src.version}",
    )


def run_golden(session: Session, version_id: str) -> golden.GoldenResult:
    v = session.get(RulebookVersion, version_id)
    if v is None:
        raise LookupError(version_id)
    result = golden.run(session, v)
    if v.status == "draft":
        v.golden_status = "green" if result.green else "red"
    session.flush()
    return result


def approve(session: Session, version_id: str, actor: str, role: str) -> RulebookVersion:
    """Approve a draft. The session must carry role 'analyst' (the trigger checks it too). Any
    approved version of the same family and jurisdiction whose dates overlap is superseded."""
    if role != "analyst":
        raise ApprovalRefused("approval needs role analyst")
    v = _draft(session, version_id)
    result = run_golden(session, version_id)
    if not result.green:
        raise ApprovalRefused(f"golden tests: {result.passed} of {result.total} passed")
    for old in session.scalars(
        select(RulebookVersion).where(
            RulebookVersion.family == v.family,
            RulebookVersion.jurisdiction_id == v.jurisdiction_id,
            RulebookVersion.status == "approved",
            RulebookVersion.id != v.id,
        )
    ):
        if old.effective_to is None or old.effective_to >= v.effective_from:
            old.status = "superseded"
    session.flush()
    v.status = "approved"
    v.approved_by = actor
    v.approved_at = datetime.now(UTC)
    session.flush()
    return v


def reject(session: Session, version_id: str) -> RulebookVersion:
    v = _draft(session, version_id)
    v.status = "rejected"
    session.flush()
    return v


def assert_session_actor(session: Session) -> str:
    actor = session.execute(text("select current_setting('ergplan.actor', true)")).scalar_one_or_none()
    if not actor:
        raise PermissionError("no actor on this session")
    return str(actor)


def day_before(d: date) -> date:
    return d - timedelta(days=1)
