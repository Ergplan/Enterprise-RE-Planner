"""G09 with a due-date rebate: the net payable is the amount payable by the due date, after
the rebate (the team, 27 Oct 2026). The clean bill passes, a planted change fails in each
input, the amount before the rebate fails. Made-up figures."""

from decimal import Decimal

from billx.core.schema import Bill, Totals
from billx.reader.validate.formula import run_checks
from billx.reader.validate.registry import CheckContext


def _bill(current="100000.00", arrears="2500.00", rebate="1000.00", net="101500.00"):
    totals = Totals(
        current_charges=Decimal(current),
        arrears_total=Decimal(arrears),
        due_date_rebate=Decimal(rebate) if rebate is not None else None,
        net_payable=Decimal(net),
    )
    return Bill(bill_type="electricity", totals=totals)


def _g09(bill):
    return next(c for c in run_checks(bill, CheckContext()) if c.id == "G09")


def test_the_net_payable_is_after_the_due_date_rebate():
    c = _g09(_bill())
    assert c.status == "pass"
    assert "totals.due_date_rebate" in c.paths


def test_a_rebate_printed_with_its_minus_sign_is_still_deducted():
    assert _g09(_bill(rebate="-1000.00")).status == "pass"


def test_a_planted_change_fails_in_each_input():
    assert _g09(_bill(current="100002.00")).status == "fail"
    assert _g09(_bill(arrears="2502.00")).status == "fail"
    assert _g09(_bill(rebate="1002.00")).status == "fail"
    assert _g09(_bill(net="101502.00")).status == "fail"


def test_the_amount_before_the_rebate_is_not_the_net_payable():
    assert _g09(_bill(net="102500.00")).status == "fail"


def test_a_bill_without_a_rebate_is_checked_as_before():
    assert _g09(_bill(rebate=None, net="102500.00")).status == "pass"
    assert _g09(_bill(rebate=None, net="101500.00")).status == "fail"
