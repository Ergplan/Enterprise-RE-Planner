"""Which rule rows apply to a connection (Stage 3). Pure.

The scope grammar and its operators live in `rulebook.scope.matches` (strict: a context missing a
constrained field never matches); this module builds the evaluation context from a connection's
facts and picks rows: the nearest jurisdiction first, then the most specific scope.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from ..rulebook.models import RuleView
from ..rulebook.scope import matches, specificity


@dataclass(frozen=True)
class ConnectionFacts:
    discom: str
    state: str
    category: str
    voltage_kv: Decimal
    connection_kind: str  # ht | eht | lt
    contract_demand_kva: Decimal | None = None
    rate_block: str | None = None  # urban | rural where the schedule splits
    consumer_kind: str | None = None


def context(c: ConnectionFacts, on: date, **extra: Any) -> dict[str, Any]:
    """The scope context for a connection on a date (month drives seasonal and ToD rows)."""
    ctx: dict[str, Any] = {
        "category": c.category,
        "voltage_kv": c.voltage_kv,
        "month": on.month,
        "date": on,
    }
    if c.rate_block:
        ctx["rate_block"] = c.rate_block
    if c.contract_demand_kva is not None:
        ctx["contract_demand_kva"] = c.contract_demand_kva
    if c.consumer_kind:
        ctx["consumer_kind"] = c.consumer_kind
    ctx.update({k: v for k, v in extra.items() if v is not None})
    return ctx


def pick(rows: Iterable[RuleView], ctx: dict[str, Any], chain: Sequence[str]) -> list[RuleView]:
    """Rows applying to ctx, nearest jurisdiction first, then most specific scope, then position."""
    rank = {j: i for i, j in enumerate(chain)}
    hits = [r for r in rows if r.jurisdiction_id in rank and matches(r.scope, ctx)]
    return sorted(hits, key=lambda r: (rank[r.jurisdiction_id], -specificity(r.scope), r.position))


def first(rows: Iterable[RuleView], ctx: dict[str, Any], chain: Sequence[str]) -> RuleView | None:
    got = pick(rows, ctx, chain)
    return got[0] if got else None
