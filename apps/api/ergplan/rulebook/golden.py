"""Golden tests: in this context, the applicable rule's field equals this printed value.

Files: packages/rulebooks/golden/<state>/<jurisdiction>-<family>.yaml

    jurisdiction: npcl
    family: tariff_schedule
    tests:
      - name: HV-2 at 11 kV energy charge
        given: {context: {category: HV-2, voltage_kv: 11}, field: /energy_charge/base}
        expect: {value: "8.32"}
        source_ref: {kind: order, document: <sha256 prefix or id>, page: 384, quote: "..."}

`expect` is one of {value: "..."} (one row applies and its field equals it, compared as decimals
when both are numbers), {absent: true} (no row applies), {count: n} (n rows apply).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..db.models import Rule, RulebookVersion, RuleTest, RuleTestRun
from .models import RuleView
from .scope import matches, specificity


@dataclass
class TestOutcome:
    name: str
    passed: bool
    actual: dict[str, Any]


@dataclass
class GoldenResult:
    total: int
    passed: int
    outcomes: list[TestOutcome] = field(default_factory=list)

    @property
    def green(self) -> bool:
        return self.total > 0 and self.passed == self.total


def golden_dir() -> Path:
    return get_settings().rulebooks_dir / "golden"


def load_files(root: Path | None = None) -> list[dict[str, Any]]:
    out = []
    for f in sorted((root or golden_dir()).rglob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        if isinstance(d, dict) and "tests" in d:
            d["_file"] = str(f)
            out.append(d)
    return out


def sync_tests(session: Session, root: Path | None = None) -> int:
    """Upsert golden tests from files (by jurisdiction, family and name). Returns the count."""
    n = 0
    for d in load_files(root):
        jid, fam = d["jurisdiction"], d["family"]
        existing = {
            t.name: t
            for t in session.scalars(
                select(RuleTest).where(RuleTest.jurisdiction_id == jid, RuleTest.family == fam)
            )
        }
        names = set()
        for t in d["tests"]:
            names.add(t["name"])
            row = existing.get(t["name"]) or RuleTest(jurisdiction_id=jid, family=fam, name=t["name"])
            row.given, row.expect, row.source_ref = t["given"], t["expect"], t.get("source_ref")
            session.add(row)
            n += 1
        for name, row in existing.items():
            if name not in names:
                session.delete(row)
    session.flush()
    return n


def _views(session: Session, v: RulebookVersion) -> list[RuleView]:
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
        )
        for r in session.scalars(select(Rule).where(Rule.rulebook_version_id == v.id).order_by(Rule.position))
    ]


def _equal(a: Any, b: Any) -> bool:
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(a).strip() == str(b).strip()


def evaluate(
    rows: list[RuleView], given: dict[str, Any], expect: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    ctx = given.get("context", {})
    hits = sorted((r for r in rows if matches(r.scope, ctx)), key=lambda r: -specificity(r.scope))
    if "absent" in expect:
        return (not hits) == bool(expect["absent"]), {"count": len(hits)}
    if "count" in expect:
        return len(hits) == int(expect["count"]), {"count": len(hits)}
    if not hits:
        return False, {"error": "no row applies"}
    top = [r for r in hits if specificity(r.scope) == specificity(hits[0].scope)]
    if len(top) > 1:
        return False, {"error": "ambiguous", "rows": [r.label or r.id for r in top]}
    value = top[0].get(given["field"])
    return _equal(value, expect["value"]), {"value": value, "row": top[0].label or top[0].id}


def run(session: Session, v: RulebookVersion) -> GoldenResult:
    tests = list(
        session.scalars(
            select(RuleTest).where(RuleTest.jurisdiction_id == v.jurisdiction_id, RuleTest.family == v.family)
        )
    )
    rows = _views(session, v)
    session.execute(delete(RuleTestRun).where(RuleTestRun.rulebook_version_id == v.id))
    res = GoldenResult(total=len(tests), passed=0)
    for t in tests:
        ok, actual = evaluate(rows, t.given, t.expect)
        session.add(RuleTestRun(rulebook_version_id=v.id, test_id=t.id, passed=ok, actual=actual))
        res.outcomes.append(TestOutcome(t.name, ok, actual))
        res.passed += int(ok)
    session.flush()
    return res
