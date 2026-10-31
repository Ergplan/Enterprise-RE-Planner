"""When a rule row applies: its `scope` against an evaluation context (scope.schema.json).

Every field the scope lists must be satisfied by the context; a field the scope omits matches
anything. A context that lacks a field the scope constrains does not match (strict), so a
question that does not say its voltage never silently gets one voltage's rate. Pure: no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

RE_SOURCES = {"solar", "wind", "hybrid"}
LIST_FIELDS = ("connection", "source", "ownership", "consumer_kind", "iex_segment")
BAND_FIELDS = ("voltage_kv", "capacity_mw", "contract_demand_kva", "load_kw")


def norm_code(text: str) -> str:
    """'HV-2', 'HV 2', 'hv2', 'HV – 2' → 'HV2'; 'HT-I (A)' → 'HTIA'."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _in_band(value: Any, band: Mapping[str, Any]) -> bool:
    v = Decimal(str(value))
    if "min" in band:
        lo = Decimal(str(band["min"]))
        if v < lo or (band.get("min_exclusive") and v == lo):
            return False
    if "max" in band:
        hi = Decimal(str(band["max"]))
        if v > hi or (band.get("max_exclusive") and v == hi):
            return False
    return True


def _source_ok(ctx_source: str, allowed: list[str]) -> bool:
    if "any" in allowed or ctx_source in allowed:
        return True
    return "any_re" in allowed and ctx_source in RE_SOURCES


def matches(scope: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
    for key, allowed in scope.items():
        if key == "commissioned":
            c = ctx.get("commissioned")
            if c is None:
                return False
            d = c if isinstance(c, date) else date.fromisoformat(str(c))
            if "from" in allowed and d < date.fromisoformat(str(allowed["from"])):
                return False
            if "to" in allowed and d > date.fromisoformat(str(allowed["to"])):
                return False
            continue
        if key == "months":
            m = ctx.get("month")
            if m is None or int(m) not in allowed:
                return False
            continue
        if key not in ctx or ctx[key] is None:
            return False
        v = ctx[key]
        if key == "source":
            if not _source_ok(str(v), list(allowed)):
                return False
        elif key in LIST_FIELDS:
            if v not in allowed:
                return False
        elif key in BAND_FIELDS:
            if not _in_band(v, allowed):
                return False
        elif key == "category":
            if norm_code(str(v)) not in {norm_code(str(a)) for a in allowed}:
                return False
        elif key in ("season", "rate_block"):
            if str(v).strip().lower() != str(allowed).strip().lower():
                return False
        else:
            return False  # an unknown scope key never matches silently
    return True


def specificity(scope: Mapping[str, Any]) -> int:
    """More constrained scopes win ties between matching rows."""
    return len(scope)
