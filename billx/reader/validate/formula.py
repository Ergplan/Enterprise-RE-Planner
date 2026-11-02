"""The formula recheck (build prompt 5.5) and `run_checks`, the one entry point that runs
every registered check for a bill (rule 8: the API, CLI, studio and evaluation all call
this).

`recheck_element` recomputes one line from its printed quantity and rate: `match`,
`differs` (with the difference as a string) or `not_computable` with a reason
(`no_quantity_or_rate`, `info_line`, `subtotal`). The tariff-order recheck is deferred:
every element's `tariff_recheck` stays `not_computable` / `tariff_engine_pending`.
"""

from __future__ import annotations

from decimal import Decimal

from billx.core.schema import Bill, CheckResult, FormulaRecheck, LineItem
from billx.reader.validate import conformance, gas, generic, tariff  # noqa: F401 - registers the checks
from billx.reader.validate.registry import ONE, CheckContext, CheckSpec, fmt, registered
from billx.reader.validate.rules import rule_spec

HUNDRED = Decimal(100)


def recheck_element(item: LineItem, bill: Bill, ctx: CheckContext) -> FormulaRecheck:
    if item.kind == "info":
        return FormulaRecheck(status="not_computable", reason="info_line")
    if item.kind == "subtotal":
        return FormulaRecheck(status="not_computable", reason="subtotal")
    if item.quantity is None or item.rate is None:
        return FormulaRecheck(status="not_computable", reason="no_quantity_or_rate")
    percent = bool(item.rate_unit and "%" in item.rate_unit)
    rate = item.rate / HUNDRED if percent else item.rate
    computed = abs(item.quantity * rate)
    billed = abs(item.amount)
    difference = billed - computed
    tolerance = ONE + ctx.tolerances.qty_x_rate_rel * billed
    formula = "quantity x rate / 100" if percent else "quantity x rate"
    return FormulaRecheck(
        status="match" if abs(difference) <= tolerance else "differs",
        computed=fmt(computed),
        billed=fmt(billed),
        difference=fmt(difference),
        formula=formula,
    )


def recheck_all(bill: Bill, ctx: CheckContext) -> tuple[FormulaRecheck, ...]:
    return tuple(recheck_element(x, bill, ctx) for x in bill.line_items)


def specs_for(bill: Bill, ctx: CheckContext) -> list[CheckSpec]:
    """Every check that applies to the bill, in id order: generic, gas, S, T from the
    registry, then the profile version's rules (R:<id>)."""
    out = [s for s in registered() if s.applies(bill.bill_type)]
    if ctx.version is not None and ctx.version.template is None:
        out = [s for s in out if not s.id.startswith("S")]
    elif ctx.version is None:
        out = [s for s in out if not s.id.startswith(("S", "T"))]
    if ctx.version is not None:
        out.extend(rule_spec(rule) for rule in ctx.version.rules)
    return out


def run_checks(bill: Bill, ctx: CheckContext | None = None) -> list[CheckResult]:
    ctx = ctx or CheckContext()
    return [s.run(bill, ctx) for s in specs_for(bill, ctx)]


__all__ = ["recheck_all", "recheck_element", "run_checks", "specs_for"]
