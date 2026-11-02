"""Layer 2, the discom's own rules (Developer Guide section 6): each rule in the profile
version is two arithmetic expressions, `actual` and `expected`, compared within a
`tolerance` (absolute) or `rel_tolerance` (a share of the expected value). The expressions
go through `billx.reader.validate.expr`, whose allow-list refuses anything that is not
arithmetic, a numeric constant or one of the helpers; everything is `Decimal`.

Result: a CheckResult with id `R:<rule id>`, `equality` true when the rule's severity is
`error`, and `proves` = the schema paths of the lines and fields the two expressions
touched (each helper records what it matched).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from billx.core.schema import Bill, CheckResult
from billx.reader.validate.expr import ExpressionError, evaluate
from billx.reader.validate.registry import (
    ZERO,
    CheckContext,
    CheckSpec,
    fmt,
    line_path,
    meter_path,
    paths_for,
    result,
    within,
)


class RuleSkip(Exception):
    """A helper found no input (an item that is not on this bill, a param not in force)."""


class RuleWarn(Exception):
    """A helper found an ambiguous input (several lines match)."""


def _ci(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


@dataclass
class Helpers:
    """The guide's helper functions bound to one bill, recording the paths they used."""

    bill: Bill
    params: dict[str, Decimal]
    paths: list[str] = field(default_factory=list)

    # the public helpers ---------------------------------------------------------------

    def field(self, path: str) -> Decimal:
        obj: Any = self.bill
        for part in path.split("."):
            if part.startswith("_") or not hasattr(obj, part):
                raise ExpressionError(f"field path {path!r} is not in the bill")
            obj = getattr(obj, part)
        if obj is None:
            raise RuleSkip(f"field_not_printed:{path}")
        if isinstance(obj, bool) or isinstance(obj, float):
            raise ExpressionError(f"field {path!r} is not a number")
        if isinstance(obj, int):
            obj = Decimal(obj)
        if not isinstance(obj, Decimal):
            raise ExpressionError(f"field {path!r} is not a number")
        self.paths.append(path)
        return obj

    def param(self, name: str) -> Decimal:
        if name not in self.params:
            raise RuleSkip(f"param_missing:{name}")
        value = self.params[name]
        if isinstance(value, bool) or isinstance(value, float):
            raise ExpressionError(f"param {name!r} is not a Decimal")
        return Decimal(value) if isinstance(value, int) else value

    def item(
        self,
        label_regex: str,
        group: str | None = None,
        kind: str | None = "item",
        stage: str | None = None,
    ) -> Decimal:
        matches = self._lines(label_regex, group, kind, stage)
        if not matches:
            raise RuleSkip("item_not_found")
        if len(matches) > 1:
            raise RuleWarn(f"item_ambiguous:{len(matches)}")
        i, x = matches[0]
        self.paths.append(line_path(i))
        return x.amount

    def items_sum(
        self,
        label_regex: str,
        group: str | None = None,
        kind: str | None = "item",
        stage: str | None = None,
    ) -> Decimal:
        matches = self._lines(label_regex, group, kind, stage)
        self.paths.extend(line_path(i) for i, _ in matches)
        return sum((x.amount for _, x in matches), ZERO)

    def subtotal(self, group_regex: str) -> Decimal:
        rx = _ci(group_regex)
        matches = [
            (i, x)
            for i, x in enumerate(self.bill.line_items)
            if x.kind == "subtotal" and (x.group and rx.search(x.group) or rx.search(x.label))
        ]
        if not matches:
            raise RuleSkip("subtotal_not_found")
        if len(matches) > 1:
            raise RuleWarn(f"subtotal_ambiguous:{len(matches)}")
        i, x = matches[0]
        self.paths.append(line_path(i))
        return x.amount

    def meter(
        self, label_regex: str, attr: str = "gross_units", quantity: str | None = None
    ) -> Decimal:
        matches = self._meters(label_regex, quantity)
        if not matches:
            raise RuleSkip("meter_not_found")
        if len(matches) > 1:
            raise RuleWarn(f"meter_ambiguous:{len(matches)}")
        i, row = matches[0]
        return self._meter_attr(i, row, attr)

    def meters_sum(
        self, label_regex: str, attr: str = "gross_units", quantity: str | None = None
    ) -> Decimal:
        total = ZERO
        for i, row in self._meters(label_regex, quantity):
            total += self._meter_attr(i, row, attr)
        return total

    @staticmethod
    def abs(x: Decimal) -> Decimal:
        return abs(x)

    @staticmethod
    def min(*xs: Decimal) -> Decimal:
        return min(xs)

    @staticmethod
    def max(*xs: Decimal) -> Decimal:
        return max(xs)

    @staticmethod
    def round(x: Decimal, places: Decimal | int = 0) -> Decimal:
        n = int(places)
        return x.quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_EVEN)

    # internals ------------------------------------------------------------------------

    def _lines(self, label_regex: str, group: str | None, kind: str | None, stage: str | None):
        rx = _ci(label_regex)
        grx = _ci(group) if group else None
        out = []
        for i, x in enumerate(self.bill.line_items):
            if not rx.search(x.label):
                continue
            if kind and x.kind != kind:
                continue
            if stage and x.stage != stage:
                continue
            if grx and not (x.group and grx.search(x.group)):
                continue
            out.append((i, x))
        return out

    def _meters(self, label_regex: str, quantity: str | None):
        rx = _ci(label_regex)
        return [
            (i, r)
            for i, r in enumerate(self.bill.meters)
            if (rx.search(r.label) or (r.tod_slot and rx.search(r.tod_slot)))
            and (quantity is None or r.quantity == quantity)
        ]

    def _meter_attr(self, i: int, row, attr: str) -> Decimal:
        if attr.startswith("_") or attr not in type(row).model_fields:
            raise ExpressionError(f"meter attribute {attr!r} does not exist")
        value = getattr(row, attr)
        if value is None:
            raise RuleSkip(f"meter_attr_not_printed:{attr}")
        if not isinstance(value, Decimal):
            raise ExpressionError(f"meter attribute {attr!r} is not a number")
        self.paths.append(meter_path(i, attr))
        return value

    def table(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "param": self.param,
            "item": self.item,
            "items_sum": self.items_sum,
            "subtotal": self.subtotal,
            "meter": self.meter,
            "meters_sum": self.meters_sum,
            "abs": self.abs,
            "min": self.min,
            "max": self.max,
            "round": self.round,
        }


def rule_spec(rule: dict) -> CheckSpec:
    severity = "fail" if rule.get("severity", "error") == "error" else "warn"
    return CheckSpec(
        id=f"R:{rule['id']}",
        description=str(rule.get("description") or rule["id"]),
        detects=str(
            rule.get("detects") or "a difference above the tolerance between actual and expected"
        ),
        run=lambda bill, ctx: evaluate_rule(rule, bill, ctx),
        proves=(),
        equality=severity == "fail",
        severity=severity,
        applies_to="both",
    )


def evaluate_rule(rule: dict, bill: Bill, ctx: CheckContext) -> CheckResult:
    s = rule_spec(rule)
    helpers = Helpers(bill, ctx.params())
    table = helpers.table()
    try:
        actual = evaluate(str(rule["actual"]), table)
        expected = evaluate(str(rule["expected"]), table)
    except RuleSkip as e:
        return result(s, "skip", note=str(e), paths=paths_for(bill, *helpers.paths))
    except RuleWarn as e:
        return result(s, "warn", note=str(e), paths=paths_for(bill, *helpers.paths))
    # an ExpressionError (a construct outside the allow-list, a bad path) propagates: it is
    # a profile bug, refused with a clear error, never a check result
    if "rel_tolerance" in rule:
        tol = Decimal(str(rule["rel_tolerance"])) * abs(expected)
    else:
        tol = Decimal(str(rule.get("tolerance", 0)))
    paths = paths_for(bill, *helpers.paths)
    ok = within(actual, expected, tol)
    return result(
        s,
        "pass" if ok else ("fail" if s.severity == "fail" else "warn"),
        expected=expected,
        actual=actual,
        tolerance=tol,
        paths=paths,
        proves=paths,
    )


def run_rules(bill: Bill, ctx: CheckContext) -> list[CheckResult]:
    if ctx.version is None:
        return []
    return [evaluate_rule(rule, bill, ctx) for rule in ctx.version.rules]


__all__ = ["Helpers", "RuleSkip", "RuleWarn", "evaluate_rule", "fmt", "rule_spec", "run_rules"]
