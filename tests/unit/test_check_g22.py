"""G22: total consumption - open-access units set off = the units the discom bills (invariant
10: the clean bill passes, a planted one-digit change fails, a missing input skips, never
passes). Made-up figures in the shape of a PVVNL open-access adjustment bill, in kVAh."""

from decimal import Decimal

from billx.core.schema import Bill, Energy
from billx.reader.validate.formula import run_checks
from billx.reader.validate.registry import CheckContext, spec


def _bill(gross="1200000", oa="250000.250", billed="949999.750", oa_unit="kVAh", **extra):
    energy = Energy(
        gross_kvah=Decimal(gross) if gross else None,
        open_access_re_kwh=Decimal(oa) if oa else None,
        open_access_unit=oa_unit,
        billed_units=Decimal(billed) if billed else None,
        billed_unit="kVAh",
        **extra,
    )
    return Bill(bill_type="electricity", energy=energy)


def _g22(bill):
    return next(c for c in run_checks(bill, CheckContext()) if c.id == "G22")


def test_the_spec_declares_what_it_detects_and_proves():
    s = spec("G22")
    assert s.equality and s.detects and s.severity == "fail"


def test_consumption_less_open_access_equals_the_grid_units():
    c = _g22(_bill())
    assert c.status == "pass"
    assert {"energy.gross_kvah", "energy.open_access_re_kwh", "energy.billed_units"} <= set(c.paths)


def test_a_planted_digit_fails_in_each_input():
    assert _g22(_bill(gross="1200600")).status == "fail"
    assert _g22(_bill(oa="250000.750")).status == "pass"  # within 1 unit
    assert _g22(_bill(oa="248000.250")).status == "fail"
    assert _g22(_bill(billed="950499.750")).status == "fail"  # a one-digit misread


def test_every_open_access_figure_is_set_off():
    bill = _bill(oa="200000", billed="949999.750", open_access_banked_kwh=Decimal("50000.250"))
    assert _g22(bill).status == "pass"


def test_missing_inputs_skip_never_pass():
    assert _g22(_bill(billed=None)).status == "skip"
    assert _g22(_bill(oa=None)).status == "skip"
    assert _g22(_bill(gross=None)).status == "skip"


def test_figures_in_different_units_are_never_compared():
    assert _g22(_bill(oa_unit="kWh")).status == "skip"
