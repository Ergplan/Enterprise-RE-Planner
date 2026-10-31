"""What the engines read (invariant 2): approved rule rows only, through the `rules_approved` view,
which itself applies the evaluation date (session variable ergplan.on_date, set here per query).
Drafts are visible only through `sandbox`."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import RuleView
from .scope import matches, specificity
from .service import jurisdiction_chain

_SQL = text(
    """
    select id, rulebook_version_id, family, position, label, scope, body, source_ref, field_refs,
           jurisdiction_id, effective_from, effective_to
    from rules_approved
    where family = :family and jurisdiction_id = any(:jids)
    order by jurisdiction_id, position
    """
)


def approved_rules(session: Session, family: str, jurisdiction_ids: list[str], on: date) -> list[RuleView]:
    session.execute(text("select set_config('ergplan.on_date', :d, true)"), {"d": on.isoformat()})
    rows = session.execute(_SQL, {"family": family, "jids": jurisdiction_ids}).mappings()
    return [
        RuleView(
            id=r["id"],
            family=r["family"],
            version_id=r["rulebook_version_id"],
            jurisdiction_id=r["jurisdiction_id"],
            scope=r["scope"] or {},
            body=r["body"] or {},
            source_ref=r["source_ref"],
            field_refs=r["field_refs"] or {},
            label=r["label"],
            position=r["position"],
            effective_from=r["effective_from"],
            effective_to=r["effective_to"],
        )
        for r in rows
    ]


def applicable(
    session: Session, family: str, jurisdiction_id: str, ctx: dict[str, Any], on: date
) -> list[RuleView]:
    """Approved rows applying to ctx, nearest jurisdiction first (DISCOM, its group, state, CERC),
    then most specific scope."""
    chain = jurisdiction_chain(session, jurisdiction_id)
    rank = {j: i for i, j in enumerate(chain)}
    hits = [r for r in approved_rules(session, family, chain, on) if matches(r.scope, ctx)]
    return sorted(hits, key=lambda r: (rank[r.jurisdiction_id], -specificity(r.scope), r.position))
