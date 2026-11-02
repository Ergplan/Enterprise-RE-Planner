"""The gas checks GG01 to GG05 (build prompt 5.4; Developer Guide section 6). The constant
of GG03 is D9's 251,995.76 kcal per MMBtu with the guide's 0.5%; the synthetic bills'
252,000 falls inside it.
"""

from __future__ import annotations

from decimal import Decimal

from billx.core.schema import Bill, CheckResult
from billx.reader.validate.registry import (
    ONE,
    ZERO,
    CheckContext,
    check,
    line_path,
    paths_for,
    result,
    skip,
    verdict,
    within,
)

KCAL_PER_MMBTU = Decimal("251995.76")  # D9
HALF_PERCENT = Decimal("0.005")


@check(
    "GG01",
    "customer id, period, net amount and volume or energy are present",
    detects="any of customer id, period from/to, net amount, or both volume and energy missing",
    applies_to="gas",
)
def gg01(bill: Bill, ctx: CheckContext) -> CheckResult:
    present = {
        "gas.customer_id": bill.gas.customer_id,
        "period.reading_from": bill.period.reading_from,
        "period.reading_to": bill.period.reading_to,
        "totals.net_payable": bill.totals.net_payable,
    }
    missing = [k for k, v in present.items() if v in (None, "")]
    if bill.gas.volume_scm is None and bill.gas.energy_mmbtu is None:
        missing.append("gas.volume_scm|gas.energy_mmbtu")
    return result(
        "GG01",
        "fail" if missing else "pass",
        paths=paths_for(bill, *present, "gas.volume_scm", "gas.energy_mmbtu"),
        note=("missing:" + ",".join(missing)) if missing else None,
    )


@check(
    "GG02",
    "(current reading - previous reading) x correction factor = volume (factor 1 when not printed)",
    detects="0.5% of the volume in either reading, the correction factor or the volume",
    proves=(
        "gas.reading_previous",
        "gas.reading_current",
        "gas.correction_factor",
        "gas.volume_scm",
    ),
    equality=True,
    applies_to="gas",
)
def gg02(bill: Bill, ctx: CheckContext) -> CheckResult:
    g = bill.gas
    if g.reading_previous is None or g.reading_current is None or g.volume_scm is None:
        return skip("GG02", "readings or volume not printed")
    factor = g.correction_factor if g.correction_factor is not None else ONE
    expected = (g.reading_current - g.reading_previous) * factor
    tol = HALF_PERCENT * abs(g.volume_scm)
    paths = ["gas.reading_previous", "gas.reading_current", "gas.volume_scm"]
    if g.correction_factor is not None:
        paths.append("gas.correction_factor")
    return result(
        "GG02",
        verdict(within(g.volume_scm, expected, tol), "fail"),
        expected=expected,
        actual=g.volume_scm,
        tolerance=tol,
        paths=paths_for(bill, *paths),
        note=None if g.correction_factor is not None else "correction_factor_not_printed",
    )


@check(
    "GG03",
    "volume x GCV / 251,995.76 = MMBtu, where all three are printed",
    detects="0.5% of the energy in volume, GCV or MMBtu",
    proves=("gas.volume_scm", "gas.gcv_kcal_per_scm", "gas.energy_mmbtu"),
    equality=True,
    applies_to="gas",
)
def gg03(bill: Bill, ctx: CheckContext) -> CheckResult:
    g = bill.gas
    if g.volume_scm is None or g.gcv_kcal_per_scm is None or g.energy_mmbtu is None:
        return skip("GG03", "volume, GCV and MMBtu not all printed")
    expected = g.volume_scm * g.gcv_kcal_per_scm / KCAL_PER_MMBTU
    tol = HALF_PERCENT * abs(g.energy_mmbtu)
    return result(
        "GG03",
        verdict(within(g.energy_mmbtu, expected, tol), "fail"),
        expected=expected,
        actual=g.energy_mmbtu,
        tolerance=tol,
        paths=paths_for(bill, "gas.volume_scm", "gas.gcv_kcal_per_scm", "gas.energy_mmbtu"),
    )


@check(
    "GG04",
    "quantity x rate = amount, per line that prints both",
    detects="Rs 1 in quantity, rate or amount of a line",
    proves=lambda b: tuple(
        line_path(i, a)
        for i, x in enumerate(b.line_items)
        if x.quantity is not None and x.rate is not None
        for a in ("quantity", "rate", "amount")
    ),
    equality=True,
    applies_to="gas",
)
def gg04(bill: Bill, ctx: CheckContext) -> CheckResult:
    checked: list[tuple[bool, Decimal, Decimal, tuple[str, ...]]] = []
    for i, x in enumerate(bill.line_items):
        if x.quantity is None or x.rate is None:
            continue
        rate = x.rate / 100 if (x.rate_unit and "%" in x.rate_unit) else x.rate
        expected = abs(x.quantity * rate)
        ps = (line_path(i, "quantity"), line_path(i, "rate"), line_path(i, "amount"))
        checked.append((within(abs(x.amount), expected, ONE), expected, abs(x.amount), ps))
    if not checked:
        return skip("GG04", "no line prints both quantity and rate")
    bad = [c for c in checked if not c[0]]
    _, expected, actual, _ = bad[0] if bad else checked[-1]
    return result(
        "GG04",
        verdict(not bad, "fail"),
        expected=expected,
        actual=actual,
        tolerance=ONE,
        paths=paths_for(bill, *(p for c in checked for p in c[3])),
        note=f"rows_checked:{len(checked)}" + (f";rows_failed:{len(bad)}" if bad else ""),
    )


@check(
    "GG05",
    "items + taxes = net amount",
    detects="Rs 1 in any line amount or in the net amount",
    proves=lambda b: (
        tuple(line_path(i) for i, x in enumerate(b.line_items) if x.kind == "item")
        + ("totals.net_payable",)
    ),
    equality=True,
    applies_to="gas",
)
def gg05(bill: Bill, ctx: CheckContext) -> CheckResult:
    items = [(i, x) for i, x in enumerate(bill.line_items) if x.kind == "item"]
    if bill.totals.net_payable is None or not items:
        return skip("GG05", "net amount or line items not printed")
    expected = sum((x.amount for _, x in items), ZERO)
    return result(
        "GG05",
        verdict(within(bill.totals.net_payable, expected, ONE), "fail"),
        expected=expected,
        actual=bill.totals.net_payable,
        tolerance=ONE,
        paths=paths_for(bill, *(line_path(i) for i, _ in items), "totals.net_payable"),
    )


__all__ = ["HALF_PERCENT", "KCAL_PER_MMBTU"]
