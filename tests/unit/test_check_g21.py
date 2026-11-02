"""G21: lines that itemise another printed line add up to it (invariant 10: the clean bill
passes, a planted one-digit change fails, a missing parent skips, never passes)."""

from decimal import Decimal

from billx.core.schema import Bill, LineItem
from billx.reader.validate.formula import run_checks
from billx.reader.validate.registry import CheckContext, spec


def _bill(tod=("1139703.63", "1277652.00", "1617097.80", "1113604.38"), parent="5148057.81"):
    lines = [
        LineItem(index=0, label="Energy Charges", amount=Decimal(parent)),
        LineItem(index=1, label="Demand Charges", amount=Decimal("1522500.00")),
    ]
    for n, amount in enumerate(tod, 1):
        lines.append(
            LineItem(
                index=len(lines),
                label=f"Time of Day (ToD) Charges TOD-{n}",
                kind="info",
                amount=Decimal(amount),
                detail_of="Energy Charges",
            )
        )
    lines.append(
        LineItem(
            index=len(lines),
            label="Fixed/Demand Charges",
            kind="info",
            quantity=Decimal("5250"),
            rate=Decimal("290"),
            amount=Decimal("1522500.00"),
            detail_of="DEMAND CHARGES",
        )
    )
    return Bill(bill_type="electricity", line_items=tuple(lines))


def _g21(bill):
    return next(c for c in run_checks(bill, CheckContext()) if c.id == "G21")


def test_the_spec_declares_what_it_detects_and_proves():
    s = spec("G21")
    assert s.equality and s.detects and s.severity == "fail"


def test_a_breakdown_that_adds_up_passes_and_proves_its_lines():
    c = _g21(_bill())
    assert c.status == "pass"
    assert "line_items[0].amount" in c.paths and "line_items[2].amount" in c.paths


def test_a_planted_digit_in_one_detail_line_fails():
    c = _g21(_bill(tod=("1139703.63", "1377652.00", "1617097.80", "1113604.38")))
    assert c.status == "fail"


def test_a_planted_digit_in_the_parent_fails():
    assert _g21(_bill(parent="5248057.81")).status == "fail"


def test_within_tolerance_still_passes():
    assert _g21(_bill(parent="5148058.81")).status == "pass"  # Rs 1 on four lines


def test_no_parent_line_is_skip_never_pass():
    bill = _bill()
    orphan = Bill(
        bill_type="electricity",
        line_items=tuple(
            x
            for x in bill.line_items
            if x.label != "Energy Charges" and x.detail_of != "DEMAND CHARGES"
        ),
    )
    assert _g21(orphan).status == "skip"


def test_detail_lines_are_not_counted_in_current_charges():
    bill = _bill()
    with_total = bill.model_copy(
        update={"totals": bill.totals.model_copy(update={"current_charges": Decimal("6670557.81")})}
    )
    g07 = next(c for c in run_checks(with_total, CheckContext()) if c.id == "G07")
    assert g07.status == "pass"


def test_a_minus_marked_detail_line_subtracts():
    """'Misc. Charges' itemised with a positive amount whose label prints '(-)'."""
    lines = (
        LineItem(index=0, label="Misc. Charges", amount=Decimal("96522.31")),
        LineItem(
            index=1,
            label="TCS Amount",
            kind="info",
            amount=Decimal("63626.20"),
            detail_of="Misc. Charges",
        ),
        LineItem(
            index=2,
            label="Due date rebate adjustment (Rs)(-)",
            kind="info",
            amount=Decimal("49818.81"),
            detail_of="Misc. Charges",
        ),
        LineItem(
            index=3,
            label="FPPA Surcharge",
            kind="info",
            amount=Decimal("82714.92"),
            detail_of="Misc. Charges",
        ),
    )
    assert _g21(Bill(bill_type="electricity", line_items=lines)).status == "pass"


def test_g05_skips_placeholder_zero_units_or_rate():
    lines = (
        LineItem(
            index=0,
            label="Electricity Duty",
            quantity=Decimal("0"),
            rate=Decimal("0"),
            amount=Decimal("506495.45"),
        ),
    )
    g05 = next(
        c
        for c in run_checks(Bill(bill_type="electricity", line_items=lines), CheckContext())
        if c.id == "G05"
    )
    assert g05.status == "skip"
