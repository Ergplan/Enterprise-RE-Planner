"""Rows of any version, drafts included. Used only by analyst endpoints and golden runs; never by
an engine serving a client (invariant 2)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Rule, RulebookVersion
from .models import RuleView


def rules(session: Session, version_id: str) -> list[RuleView]:
    v = session.get(RulebookVersion, version_id)
    if v is None:
        raise LookupError(version_id)
    return [
        RuleView(
            id=r.id,
            family=r.family,
            version_id=v.id,
            jurisdiction_id=v.jurisdiction_id,
            scope=r.scope,
            body=r.body,
            source_ref=r.source_ref,
            field_refs=r.field_refs or {},
            label=r.label,
            position=r.position,
            effective_from=v.effective_from,
            effective_to=v.effective_to,
        )
        for r in session.scalars(select(Rule).where(Rule.rulebook_version_id == v.id).order_by(Rule.position))
    ]
