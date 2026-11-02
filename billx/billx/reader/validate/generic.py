"""Layer 1, the generic checks G01 to G20 (build prompt 5.4; Developer Guide section 6).

Each check declares what it `detects` and, when it is an equality check, which paths it
`proves`; `tests/unit/test_checks_planted.py` plants a misread at the declared position and
asserts the check catches it. A check whose inputs are not printed reports `skip`.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from billx.core.schema import Bill, CheckResult, LineItem, MeterRow
from billx.reader.validate.registry import (
    ONE,
    ZERO,
    CheckContext,
    CheckSpec,
    check,
    energy_path,
    fmt,
    line_path,
    meter_path,
    paths_for,
    result,
    skip,
    spec,
    verdict,
    within,
)

CENT = Decimal("0.01")
RATE_006 = Decimal("0.006")
G02_TOL = Decimal("0.011")
G11_TOL = Decimal("0.006")
ONE_PERCENT = Decimal("0.01")
# A label that marks its own amount as a subtraction: the amount is printed positive and the
# sign is in the label ("Due date rebate adjustment (Rs)(-)", "Subsidy by Govt. (-)").
MINUS_LABEL = re.compile(r"\(\s*-\s*\)|\(\s*minus\s*\)", re.IGNORECASE)


def signed_amount(x: LineItem) -> Decimal:
    """A line's amount as it adds into a total: negative when its label prints the minus."""
    if x.amount > ZERO and MINUS_LABEL.search(x.label):
        return -x.amount
    return x.amount


CREDIT_LABEL = re.compile(
    r"rebate|credit|incentive|refund|discount|subsid|adjust|less\b|\bcr\b|minus|"
    r"net metering|export|waiver|concession|reversal|excess payment|advance",
    re.IGNORECASE,
)


# helpers ------------------------------------------------------------------------------------


def _month_index(ym: str | None) -> int | None:
    if not ym:
        return None
    m = re.match(r"^(\d{4})-(\d{2})", ym)
    if not m:
        return None
    return int(m.group(1)) * 12 + int(m.group(2)) - 1


def _date(iso: str | None) -> date | None:
    if not iso:
        return None
    try:
        return date.fromisoformat(iso)
    except ValueError:
        return None


def _mf(row: MeterRow) -> Decimal:
    return row.multiplying_factor if row.multiplying_factor is not None else ONE


def _slot_rows(bill: Bill, quantity: str) -> list[tuple[int, MeterRow]]:
    return [(i, r) for i, r in enumerate(bill.meters) if r.quantity == quantity and r.tod_slot]


def _total_row(bill: Bill, quantity: str) -> tuple[int, MeterRow] | None:
    rows = [(i, r) for i, r in enumerate(bill.meters) if r.quantity == quantity and not r.tod_slot]
    return rows[0] if len(rows) == 1 else None


def _items(bill: Bill, stage: str | None = None) -> list[tuple[int, LineItem]]:
    return [
        (i, x)
        for i, x in enumerate(bill.line_items)
        if x.kind == "item" and (stage is None or x.stage == stage)
    ]


def _sum_tolerance(n: int) -> Decimal:
    return max(ONE, CENT * n)


def _rows_result(
    s: CheckSpec,
    bill: Bill,
    checked: list[tuple[bool, Decimal, Decimal, Decimal, tuple[str, ...]]],
    skip_note: str,
) -> CheckResult:
    """Combine per-row comparisons: skip when none, fail on the first mismatch."""
    if not checked:
        return skip(s, skip_note)
    paths = tuple(p for _, _, _, _, ps in checked for p in ps)
    bad = [c for c in checked if not c[0]]
    ok, expected, actual, tol, _ = bad[0] if bad else checked[-1]
    return result(
        s,
        verdict(not bad, s.severity),
        expected=expected,
        actual=actual,
        tolerance=tol,
        paths=paths_for(bill, *paths),
        note=f"rows_checked:{len(checked)}" + (f";rows_failed:{len(bad)}" if bad else ""),
    )


# G01 - G09 ----------------------------------------------------------------------------------


@check(
    "G01",
    "utility name, account number, bill month and net payable are present",
    detects="any of the four identity or money fields missing from the transcription",
)
def g01(bill: Bill, ctx: CheckContext) -> CheckResult:
    present = {
        "discom.name_as_printed": bill.discom.name_as_printed,
        "consumer.account_number": bill.consumer.account_number
        or bill.consumer.service_connection_number,
        "period.bill_month": bill.period.bill_month,
        "totals.net_payable": bill.totals.net_payable,
    }
    missing = tuple(k for k, v in present.items() if v in (None, ""))
    return result(
        "G01",
        "fail" if missing else "pass",
        paths=paths_for(bill, *present),
        note=("missing:" + ",".join(missing)) if missing else None,
    )


@check(
    "G02",
    "present - past = difference, per meter row",
    detects="0.011 in any of present, past or difference of a meter row",
    proves=lambda b: tuple(
        meter_path(i, a) for i, r in enumerate(b.meters) for a in ("present", "past", "difference")
    ),
    equality=True,
)
def g02(bill: Bill, ctx: CheckContext) -> CheckResult:
    checked = []
    for i, r in enumerate(bill.meters):
        if r.present is None or r.past is None or r.difference is None:
            continue
        expected = r.present - r.past
        ps = (meter_path(i, "present"), meter_path(i, "past"), meter_path(i, "difference"))
        checked.append(
            (within(r.difference, expected, G02_TOL), expected, r.difference, G02_TOL, ps)
        )
    return _rows_result(
        spec("G02"), bill, checked, "no meter row prints present, past and difference"
    )


@check(
    "G03",
    "difference x MF = gross units, per meter row; the total register also equals the energy field",
    detects="a change of max(1, 0.006 x MF) in gross units or 0.006 in difference",
    proves=lambda b: (
        tuple(
            meter_path(i, a)
            for i, r in enumerate(b.meters)
            for a in ("difference", "multiplying_factor", "gross_units")
        )
        + ("energy.gross_kwh", "energy.gross_kvah")
    ),
    equality=True,
)
def g03(bill: Bill, ctx: CheckContext) -> CheckResult:
    checked = []
    for i, r in enumerate(bill.meters):
        if r.difference is None or r.multiplying_factor is None or r.gross_units is None:
            continue
        expected = r.difference * r.multiplying_factor
        tol = max(ONE, RATE_006 * r.multiplying_factor)
        ps: tuple[str, ...] = (
            meter_path(i, "difference"),
            meter_path(i, "multiplying_factor"),
            meter_path(i, "gross_units"),
        )
        ok = within(r.gross_units, expected, tol)
        energy = energy_path(r.quantity)
        if not r.tod_slot and energy:
            total = getattr(bill.energy, energy.split(".")[1])
            if total is not None:
                ok = ok and within(total, expected, tol)
                ps += (energy,)
        checked.append((ok, expected, r.gross_units, tol, ps))
    return _rows_result(
        spec("G03"), bill, checked, "no meter row prints difference, MF and gross units"
    )


@check(
    "G04",
    "gross units - open access units = net units, per meter row",
    detects="1 unit in gross, open access or net units of a meter row",
    proves=lambda b: tuple(
        meter_path(i, a)
        for i, r in enumerate(b.meters)
        for a in ("gross_units", "open_access_units", "net_units")
    ),
    equality=True,
)
def g04(bill: Bill, ctx: CheckContext) -> CheckResult:
    checked = []
    for i, r in enumerate(bill.meters):
        if r.gross_units is None or r.open_access_units is None or r.net_units is None:
            continue
        expected = r.gross_units - r.open_access_units
        ps = (
            meter_path(i, "gross_units"),
            meter_path(i, "open_access_units"),
            meter_path(i, "net_units"),
        )
        checked.append((within(r.net_units, expected, ONE), expected, r.net_units, ONE, ps))
    return _rows_result(spec("G04"), bill, checked, "no meter row prints open access and net units")


def _is_percent(x: LineItem) -> bool:
    return bool(x.rate_unit and "%" in x.rate_unit)


@check(
    "G05",
    "|quantity x rate| = |amount| for every line that prints both (a % rate divided by 100)",
    detects=(
        "Rs 1 (plus the profile's qty_x_rate_rel share of the amount) in quantity, rate or "
        "amount of a line"
    ),
    proves=lambda b: tuple(
        line_path(i, a)
        for i, x in enumerate(b.line_items)
        if x.quantity is not None and x.rate is not None
        for a in ("quantity", "rate", "amount")
    ),
    equality=True,
)
def g05(bill: Bill, ctx: CheckContext) -> CheckResult:
    checked = []
    for i, x in enumerate(bill.line_items):
        if x.quantity is None or x.rate is None:
            continue
        if (x.quantity == ZERO or x.rate == ZERO) and x.amount != ZERO:
            continue  # "0.00" printed in an empty units or rate column is a placeholder
        rate = x.rate / 100 if _is_percent(x) else x.rate
        expected = abs(x.quantity * rate)
        tol = ONE + ctx.tolerances.qty_x_rate_rel * abs(x.amount)
        ps = (line_path(i, "quantity"), line_path(i, "rate"), line_path(i, "amount"))
        checked.append((within(abs(x.amount), expected, tol), expected, abs(x.amount), tol, ps))
    return _rows_result(spec("G05"), bill, checked, "no line prints both quantity and rate")


@check(
    "G06",
    "items of a group = the group's printed subtotal",
    detects="max(Rs 1, Rs 0.01 per item) in any item amount of the group or in its subtotal",
    proves=lambda b: tuple(
        line_path(i)
        for i, x in enumerate(b.line_items)
        if x.group and any(s.kind == "subtotal" and s.group == x.group for s in b.line_items)
    ),
    equality=True,
)
def g06(bill: Bill, ctx: CheckContext) -> CheckResult:
    """Items of a group against its one printed subtotal, stage for stage: a current-stage
    subtotal ("Current Charges") sums the group's current items, never its arrear line. A
    group that prints several subtotals (a section total and a net payable, say) is left to
    G07 to G09, which know what each total means."""
    checked = []
    subtotals = [(i, x) for i, x in enumerate(bill.line_items) if x.kind == "subtotal" and x.group]
    groups = [x.group for _, x in subtotals]
    for si, sub in subtotals:
        if groups.count(sub.group) > 1:
            continue
        items = [
            (i, x)
            for i, x in enumerate(bill.line_items)
            if x.kind == "item" and x.group == sub.group and x.stage == sub.stage
        ]
        if not items:
            continue
        expected = sum((signed_amount(x) for _, x in items), ZERO)
        tol = _sum_tolerance(len(items))
        ps = tuple(line_path(i) for i, _ in items) + (line_path(si),)
        checked.append((within(sub.amount, expected, tol), expected, sub.amount, tol, ps))
    return _rows_result(spec("G06"), bill, checked, "no group prints a subtotal")


@check(
    "G07",
    "current-stage items = totals.current_charges",
    detects="max(Rs 1, Rs 0.01 per item) in any current item amount or in current charges",
    proves=lambda b: (
        tuple(line_path(i) for i, _ in _items(b, "current")) + ("totals.current_charges",)
    ),
    equality=True,
)
def g07(bill: Bill, ctx: CheckContext) -> CheckResult:
    items = _items(bill, "current")
    if bill.totals.current_charges is None or not items:
        return skip("G07", "current charges or current items not printed")
    expected = sum((signed_amount(x) for _, x in items), ZERO)
    tol = _sum_tolerance(len(items))
    paths = paths_for(bill, *(line_path(i) for i, _ in items), "totals.current_charges")
    ok = within(bill.totals.current_charges, expected, tol)
    return result(
        "G07",
        verdict(ok, "fail"),
        expected=expected,
        actual=bill.totals.current_charges,
        tolerance=tol,
        paths=paths,
    )


@check(
    "G08",
    "arrear-stage items = totals.arrears_total",
    detects="max(Rs 1, Rs 0.01 per item) in any arrear item amount or in the arrears total",
    proves=lambda b: (
        tuple(line_path(i) for i, _ in _items(b, "arrear")) + ("totals.arrears_total",)
    ),
    equality=True,
)
def g08(bill: Bill, ctx: CheckContext) -> CheckResult:
    if bill.totals.arrears_total is None:
        return skip("G08", "arrears total not printed")
    items = _items(bill, "arrear")
    expected = sum((signed_amount(x) for _, x in items), ZERO)
    tol = _sum_tolerance(max(1, len(items)))
    paths = paths_for(bill, *(line_path(i) for i, _ in items), "totals.arrears_total")
    ok = within(bill.totals.arrears_total, expected, tol)
    return result(
        "G08",
        verdict(ok, "fail"),
        expected=expected,
        actual=bill.totals.arrears_total,
        tolerance=tol,
        paths=paths,
    )


@check(
    "G09",
    "current charges + arrears + adjustments - due-date rebate = net payable",
    detects="Rs 1 in any of current charges, arrears, adjustments, due-date rebate or net payable",
    proves=(
        "totals.current_charges",
        "totals.arrears_total",
        "totals.adjustments_total",
        "totals.due_date_rebate",
        "totals.net_payable",
    ),
    equality=True,
)
def g09(bill: Bill, ctx: CheckContext) -> CheckResult:
    t = bill.totals
    if t.current_charges is None or t.net_payable is None:
        return skip("G09", "current charges or net payable not printed")
    parts = ["totals.current_charges"]
    expected = t.current_charges
    if t.arrears_total is not None:
        expected += t.arrears_total
        parts.append("totals.arrears_total")
    if t.adjustments_total is not None:
        expected += t.adjustments_total
        parts.append("totals.adjustments_total")
    # the net payable is the amount payable by the due date, after the due-date rebate
    # (the team, 27 Oct 2026); the rebate is printed as a positive amount or with its sign
    if t.due_date_rebate is not None:
        expected -= abs(t.due_date_rebate)
        parts.append("totals.due_date_rebate")
    parts.append("totals.net_payable")
    ok = within(t.net_payable, expected, ONE)
    return result(
        "G09",
        verdict(ok, "fail"),
        expected=expected,
        actual=t.net_payable,
        tolerance=ONE,
        paths=paths_for(bill, *parts),
        note=None if t.arrears_total is not None else "arrears_not_printed",
    )


# G10 - G14 (warnings) -----------------------------------------------------------------------


@check(
    "G10",
    "billing demand >= minimum billable and = max(recorded MD, minimum billable)",
    detects="1% of the billing demand in recorded MD, minimum billable or billing demand",
    severity="warn",
)
def g10(bill: Bill, ctx: CheckContext) -> CheckResult:
    d, c = bill.demand, bill.connection
    if d.billing_kva is None or (d.recorded_kva is None and c.minimum_billable_kva is None):
        return skip("G10", "billing demand, recorded MD or minimum billable not printed")
    tol = ONE_PERCENT * abs(d.billing_kva)
    paths = ["demand.billing_kva"]
    if c.minimum_billable_kva is not None and d.recorded_kva is not None:
        expected = max(d.recorded_kva, c.minimum_billable_kva)
        paths += ["demand.recorded_kva", "connection.minimum_billable_kva"]
        ok = within(d.billing_kva, expected, tol) and d.billing_kva + tol >= c.minimum_billable_kva
        note = None
    elif d.recorded_kva is not None:
        expected = d.recorded_kva
        paths.append("demand.recorded_kva")
        ok = d.billing_kva + tol >= d.recorded_kva
        note = "minimum_not_printed"
    else:
        expected = c.minimum_billable_kva
        paths.append("connection.minimum_billable_kva")
        ok = d.billing_kva + tol >= expected
        note = "recorded_md_not_printed"
    return result(
        "G10",
        verdict(ok, "warn"),
        expected=expected,
        actual=d.billing_kva,
        tolerance=tol,
        paths=paths_for(bill, *paths),
        note=note,
    )


@check(
    "G11",
    "power factor = gross kWh / gross kVAh",
    detects="0.006 in the printed power factor against the ratio of the gross registers",
    severity="warn",
)
def g11(bill: Bill, ctx: CheckContext) -> CheckResult:
    e = bill.energy
    if e.power_factor is None or e.gross_kwh is None or e.gross_kvah in (None, ZERO):
        return skip("G11", "power factor or the gross registers not printed")
    expected = e.gross_kwh / e.gross_kvah
    ok = within(e.power_factor, expected, G11_TOL)
    return result(
        "G11",
        verdict(ok, "warn"),
        expected=expected,
        actual=e.power_factor,
        tolerance=G11_TOL,
        paths=paths_for(bill, "energy.power_factor", "energy.gross_kwh", "energy.gross_kvah"),
    )


@check(
    "G12",
    "due date after bill date; billing days match the reading period",
    detects="a due date on or before the bill date, or 1 day in the printed billing days",
    severity="warn",
)
def g12(bill: Bill, ctx: CheckContext) -> CheckResult:
    p = bill.period
    bill_date, due, start, end = (
        _date(p.bill_date),
        _date(p.due_date),
        _date(p.reading_from),
        _date(p.reading_to),
    )
    paths: list[str] = []
    problems: list[str] = []
    checked = False
    if bill_date and due:
        checked = True
        paths += ["period.bill_date", "period.due_date"]
        if due <= bill_date:
            problems.append("due_not_after_bill_date")
    expected = actual = None
    if p.billing_days is not None and start and end:
        checked = True
        paths += ["period.billing_days", "period.reading_from", "period.reading_to"]
        expected = Decimal((end - start).days + 1)
        actual = Decimal(p.billing_days)
        if abs(actual - expected) > ONE:
            problems.append("billing_days_mismatch")
    if not checked:
        return skip("G12", "dates or billing days not printed")
    return result(
        "G12",
        verdict(not problems, "warn"),
        expected=expected,
        actual=actual,
        tolerance=ONE,
        paths=paths_for(bill, *paths),
        note=",".join(problems) or None,
    )


@check(
    "G13",
    "billed units within 0.33 to 3 times the history median",
    detects="billed units outside 0.33 to 3 times the median of the printed history",
    severity="warn",
)
def g13(bill: Bill, ctx: CheckContext) -> CheckResult:
    units = [h.units for h in bill.history if h.units is not None and h.units > ZERO]
    billed = (
        bill.energy.billed_units if bill.energy.billed_units is not None else bill.energy.gross_kwh
    )
    if not units or billed is None:
        return skip("G13", "no history or no billed units")
    s = sorted(units)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    ok = Decimal("0.33") * median <= billed <= Decimal(3) * median
    return result(
        "G13",
        verdict(ok, "warn"),
        expected=median,
        actual=billed,
        paths=paths_for(bill, "energy.billed_units", "energy.gross_kwh", "history"),
    )


@check(
    "G14",
    "the model wrote extraction notes",
    detects="any extraction note (a warning that something was unreadable or ambiguous)",
    severity="warn",
)
def g14(bill: Bill, ctx: CheckContext) -> CheckResult:
    n = len(bill.extraction_notes)
    return result(
        "G14",
        "warn" if n else "pass",
        paths=("extraction_notes",),
        note=f"notes:{n}" if n else None,
    )


# G15 - G20 ----------------------------------------------------------------------------------


def _g15_proves(b: Bill) -> tuple[str, ...]:
    out: list[str] = []
    for q in ("kWh", "kVAh"):
        slots = _slot_rows(b, q)
        if not slots:
            continue
        out += [meter_path(i, "gross_units") for i, _ in slots]
        total = _total_row(b, q)
        if total:
            out.append(meter_path(total[0], "gross_units"))
        out.append(energy_path(q) or "")
    return tuple(p for p in out if p)


@check(
    "G15",
    "TOD slot units add up to the total register of the same quantity",
    detects="max(1, 0.006 x MF x slots) in any slot's gross units or in the total register",
    proves=_g15_proves,
    equality=True,
)
def g15(bill: Bill, ctx: CheckContext) -> CheckResult:
    complete = bool(ctx.version and ctx.version.tod_complete)
    checked = []
    for q in ("kWh", "kVAh"):
        slots = [(i, r) for i, r in _slot_rows(bill, q) if r.gross_units is not None]
        if not slots:
            continue
        total = _total_row(bill, q)
        energy = energy_path(q)
        energy_value = getattr(bill.energy, energy.split(".")[1]) if energy else None
        ps = tuple(meter_path(i, "gross_units") for i, _ in slots)
        targets: list[tuple[Decimal, str]] = []
        if total and total[1].gross_units is not None:
            targets.append((total[1].gross_units, meter_path(total[0], "gross_units")))
        if energy_value is not None and energy:
            targets.append((energy_value, energy))
        if not targets:
            continue
        mf = _mf(total[1]) if total else _mf(slots[0][1])
        tol = max(ONE, RATE_006 * mf * len(slots))
        expected = sum((r.gross_units for _, r in slots), ZERO)
        ok = all(within(t, expected, tol) for t, _ in targets)
        checked.append((ok, expected, targets[0][0], tol, ps + tuple(p for _, p in targets)))
    r = _rows_result(
        spec("G15"), bill, checked, "no TOD slot rows with a total register or energy field"
    )
    if r.status == "fail" and not complete:
        return r.model_copy(
            update={"status": "warn", "note": (r.note or "") + ";tod_complete_not_declared"}
        )
    return r


@check(
    "G16",
    "gross kVAh >= gross kWh (both printed, no net metering)",
    detects="a kVAh total misread below the kWh total by more than max(1, 0.006 x MF)",
)
def g16(bill: Bill, ctx: CheckContext) -> CheckResult:
    e = bill.energy
    if e.gross_kwh is None or e.gross_kvah is None:
        return skip("G16", "gross kWh and kVAh not both printed")
    if e.net_metering_import_kwh is not None or e.net_metering_export_kwh is not None:
        return skip("G16", "net metering printed")
    total = _total_row(bill, "kWh")
    mf = _mf(total[1]) if total else ONE
    tol = max(ONE, RATE_006 * mf)
    ok = e.gross_kvah + tol >= e.gross_kwh
    return result(
        "G16",
        verdict(ok, "fail"),
        expected=e.gross_kwh,
        actual=e.gross_kvah,
        tolerance=tol,
        paths=paths_for(bill, "energy.gross_kwh", "energy.gross_kvah"),
    )


@check(
    "G17",
    "net metering: import - export = net units billed",
    detects="max(1, 0.006 x MF) in import, export or billed units",
    proves=(
        "energy.net_metering_import_kwh",
        "energy.net_metering_export_kwh",
        "energy.billed_units",
    ),
    equality=True,
)
def g17(bill: Bill, ctx: CheckContext) -> CheckResult:
    e = bill.energy
    if (
        e.net_metering_import_kwh is None
        or e.net_metering_export_kwh is None
        or e.billed_units is None
    ):
        return skip("G17", "net metering import, export or billed units not printed")
    total = _total_row(bill, "kWh")
    mf = _mf(total[1]) if total else ONE
    tol = max(ONE, RATE_006 * mf)
    expected = e.net_metering_import_kwh - e.net_metering_export_kwh
    ok = within(e.billed_units, expected, tol)
    return result(
        "G17",
        verdict(ok, "fail"),
        expected=expected,
        actual=e.billed_units,
        tolerance=tol,
        paths=paths_for(
            bill,
            "energy.net_metering_import_kwh",
            "energy.net_metering_export_kwh",
            "energy.billed_units",
        ),
    )


@check(
    "G18",
    "bill month in the reading period, or within bill_month_offset months after it",
    detects="a bill month outside [from month + lo, to month + hi] (default 0..1)",
)
def g18(bill: Bill, ctx: CheckContext) -> CheckResult:
    p = bill.period
    bm = _month_index(p.bill_month)
    start, end = _date(p.reading_from), _date(p.reading_to)
    if bm is None or start is None or end is None:
        return skip("G18", "bill month or reading period not printed")
    lo, hi = ctx.version.bill_month_offset if ctx.version else (0, 1)
    low = start.year * 12 + start.month - 1 + lo
    high = end.year * 12 + end.month - 1 + hi
    ok = low <= bm <= high
    return result(
        "G18",
        verdict(ok, "fail"),
        expected=f"{lo}..{hi} months after the period",
        actual=p.bill_month,
        paths=paths_for(bill, "period.bill_month", "period.reading_from", "period.reading_to"),
    )


@check(
    "G19",
    "reading period start is before its end",
    detects="a start date on or after the end date (swapped or misread dates)",
)
def g19(bill: Bill, ctx: CheckContext) -> CheckResult:
    start, end = _date(bill.period.reading_from), _date(bill.period.reading_to)
    if start is None or end is None:
        return skip("G19", "reading period not printed")
    return result(
        "G19",
        verdict(start < end, "fail"),
        expected=bill.period.reading_to,
        actual=bill.period.reading_from,
        paths=paths_for(bill, "period.reading_from", "period.reading_to"),
    )


@check(
    "G20",
    "a negative amount sits on a credit, rebate, arrear or adjustment line, or a line the "
    "layout marks signed",
    detects=(
        "a minus sign read into the amount of a line that is not a credit, rebate or signed line"
    ),
)
def g20(bill: Bill, ctx: CheckContext) -> CheckResult:
    bad: list[str] = []
    for i, x in enumerate(bill.line_items):
        signed_stage = x.stage in ("arrear", "adjustment")  # an advance or carried credit
        if (
            x.amount < ZERO
            and not x.signed
            and not signed_stage
            and not CREDIT_LABEL.search(x.label)
        ):
            bad.append(line_path(i))
    for i, x in enumerate(bill.line_items):
        if x.quantity is not None and x.quantity < ZERO and not x.signed:
            bad.append(line_path(i, "quantity"))
    for i, r in enumerate(bill.meters):
        for attr in ("present", "past", "difference", "gross_units"):
            v = getattr(r, attr)
            if v is not None and v < ZERO:
                bad.append(meter_path(i, attr))
    paths = tuple(line_path(i) for i in range(len(bill.line_items)))
    return result(
        "G20",
        "fail" if bad else "pass",
        paths=paths_for(bill, *(bad or paths)),
        note=("negative:" + ",".join(bad)) if bad else None,
    )


def _label_key(text: str | None) -> str:
    """A label for matching, not for display: case, punctuation and spacing ignored."""
    return re.sub(r"[^A-Z0-9]+", " ", (text or "").upper()).strip()


def _details(bill: Bill) -> dict[str, list[tuple[int, LineItem]]]:
    out: dict[str, list[tuple[int, LineItem]]] = {}
    for i, x in enumerate(bill.line_items):
        if x.detail_of:
            out.setdefault(_label_key(x.detail_of), []).append((i, x))
    return out


def _parent(bill: Bill, key: str) -> tuple[int, LineItem] | None:
    """The one printed line a breakdown details: an item or subtotal (never itself a detail
    line) whose label matches, exactly or by containment. None when there is no such line or
    more than one."""
    exact, near = [], []
    for i, x in enumerate(bill.line_items):
        if x.detail_of or x.kind == "info":
            continue
        k = _label_key(x.label)
        if k == key:
            exact.append((i, x))
        elif key and k and (key in k or k in key):
            near.append((i, x))
    found = exact or near
    return found[0] if len(found) == 1 else None


@check(
    "G21",
    "lines that itemise another printed line add up to it (a calculation or details table "
    "against its summary line)",
    detects="max(Rs 1, Rs 0.01 per line) in a detail line's amount or in the line it details",
    proves=lambda b: tuple(line_path(i) for i, x in enumerate(b.line_items) if x.detail_of),
    equality=True,
)
def g21(bill: Bill, ctx: CheckContext) -> CheckResult:
    checked = []
    for key, details in _details(bill).items():
        parent = _parent(bill, key)
        if parent is None:
            continue
        pi, px = parent
        expected = sum((signed_amount(x) for _, x in details), ZERO)
        tol = _sum_tolerance(len(details))
        ps = tuple(line_path(i) for i, _ in details) + (line_path(pi),)
        checked.append((within(px.amount, expected, tol), expected, px.amount, tol, ps))
    return _rows_result(spec("G21"), bill, checked, "no line itemises another printed line")


_OPEN_ACCESS = (
    "energy.open_access_re_kwh",
    "energy.open_access_non_re_kwh",
    "energy.open_access_banked_kwh",
)


@check(
    "G22",
    "total consumption - open-access units set off = units billed by the discom (grid units)",
    detects="1 unit in the total consumption, an open-access figure or the billed units",
    proves=("energy.gross_kwh", "energy.gross_kvah", *_OPEN_ACCESS, "energy.billed_units"),
    equality=True,
)
def g22(bill: Bill, ctx: CheckContext) -> CheckResult:
    e = bill.energy
    oa = {
        p: getattr(e, p.split(".")[1])
        for p in _OPEN_ACCESS
        if getattr(e, p.split(".")[1]) is not None
    }
    if e.billed_units is None or not oa:
        return skip("G22", "billed units or open-access units not printed")
    unit = e.billed_unit
    gross_path = energy_path(unit) if unit else None
    if gross_path is None or e.open_access_unit != unit:
        return skip("G22", "billed and open-access units are printed in different units")
    gross = getattr(e, gross_path.split(".")[1])
    if gross is None:
        return skip("G22", f"total consumption in {unit} not printed")
    expected = gross - sum(oa.values(), ZERO)
    return result(
        "G22",
        verdict(within(e.billed_units, expected, ONE), "fail"),
        expected=expected,
        actual=e.billed_units,
        tolerance=ONE,
        paths=paths_for(bill, gross_path, *oa, "energy.billed_units"),
    )


__all__ = ["CREDIT_LABEL", "fmt"]
