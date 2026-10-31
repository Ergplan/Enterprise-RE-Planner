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


_PINNED_SQL = text(
    """
    select r.id, r.rulebook_version_id, r.family, r.position, r.label, r.scope, r.body, r.source_ref,
           r.field_refs, v.jurisdiction_id, v.effective_from, v.effective_to
    from rules r join rulebook_versions v on v.id = r.rulebook_version_id
    where r.family = :family and v.jurisdiction_id = any(:jids) and v.id = any(:vids)
      and v.status in ('approved', 'superseded')
      and v.effective_from <= :on and (v.effective_to is null or v.effective_to >= :on)
    order by v.jurisdiction_id, r.position
    """
)


def pinned_rules(
    session: Session, family: str, jurisdiction_ids: list[str], on: date, version_ids: list[str]
) -> list[RuleView]:
    """Replay only (invariant 5): the rows of the versions a run pinned — approved when the run was
    made, approved or superseded now; never a draft — effective on the date."""
    rows = session.execute(
        _PINNED_SQL, {"family": family, "jids": jurisdiction_ids, "vids": version_ids, "on": on}
    ).mappings()
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


class Reader:
    """What a run reads rules through: approved rows, recording every version loaded (the run's pins),
    or — for a replay — only the pinned versions."""

    def __init__(self, pins: list[str] | None = None) -> None:
        self.pins = pins
        self.used: set[str] = set()

    def __call__(
        self, session: Session, family: str, jurisdiction_ids: list[str], on: date
    ) -> list[RuleView]:
        if self.pins is None:
            rows = approved_rules(session, family, jurisdiction_ids, on)
        else:
            rows = pinned_rules(session, family, jurisdiction_ids, on, self.pins)
        self.used.update(r.version_id for r in rows)
        return rows
