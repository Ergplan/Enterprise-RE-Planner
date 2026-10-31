"""Approved rulebooks for engine tests: the committed exports restored into the test database."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ergplan.core.sourced import RefKind, SourcedValue, SourceRef
from ergplan.core.units import Unit
from ergplan.db.base import session_scope
from ergplan.engine import scope as escope
from ergplan.engine.avoided_cost import MonthRules
from ergplan.rulebook import golden, repository, service, yaml_io
from ergplan.rulebook.models import RuleView


def restore_committed() -> None:
    with session_scope(actor="ci") as s:
        service.sync_jurisdictions(s)
        golden.sync_tests(s)
    for p in sorted(yaml_io.states_dir().rglob("*.yaml")):
        d = yaml_io.load(p)
        with session_scope(actor=d.get("approved_by") or "ci", role="analyst") as s:
            yaml_io.restore(s, p)


def rules(discom: str, category: str, kv: str, on: date, rate_block: str | None = "urban") -> MonthRules:
    facts = escope.ConnectionFacts(
        discom=discom,
        state="",
        category=category,
        voltage_kv=Decimal(kv),
        connection_kind="ht",
        rate_block=rate_block,
    )
    with session_scope() as s:
        chain = service.jurisdiction_chain(s, discom)
        ctx = escope.context(facts, on)
        ts = repository.approved_rules(s, "tariff_schedule", chain, on)
        td = repository.approved_rules(s, "tod_slots", chain, on)
        return MonthRules(escope.first(ts, ctx, chain), escope.first(td, ctx, chain))


def sv(value: str, unit: Unit, note: str = "test") -> SourcedValue:
    return SourcedValue(
        value=Decimal(value), unit=unit, source_refs=(SourceRef(kind=RefKind.CLIENT_STATED, note=note),)
    )


def schedule(r: MonthRules) -> RuleView:
    assert r.schedule is not None
    return r.schedule
