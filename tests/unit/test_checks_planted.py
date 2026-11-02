"""Planted misreads (invariant 10): for every check with severity fail, the clean synthetic
bill passes (or skips where the layout does not print the input), one digit changed at the
position the check's `detects:` declares makes that exact check fail, a change inside the
tolerance still passes, and a missing input makes the check skip, never pass."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal

import pytest
from _checks_support import (
    clean_bills,
    context_for,
    electricity_truths,
    gas_truths,
    leading_digit_changed,
    line_index,
    meter_index,
    results,
    total_rows,
    with_line,
    with_meter,
    with_section,
    with_totals,
)

from billx.core.schema import Bill, LineItem, MeterRow
from billx.platform.synth.to_bill import bill_from_truth
from billx.reader.validate.registry import CheckContext, Tolerances, registered

TWO = Decimal(2)
ELECTRICITY = [bill_from_truth(t) for t in electricity_truths()]
GAS = [bill_from_truth(t) for t in gas_truths()]
E_IDS = [f"{b.discom.name_as_printed}-{b.period.bill_month}-{i}" for i, b in enumerate(ELECTRICITY)]
G_IDS = [f"{b.discom.name_as_printed}-{i}" for i, b in enumerate(GAS)]
MUST_PASS_ELECTRICITY = (
    "G01",
    "G02",
    "G03",
    "G05",
    "G07",
    "G08",
    "G09",
    "G15",
    "G16",
    "G18",
    "G19",
    "G20",
)
MUST_PASS_GAS = ("GG01", "GG02", "GG03", "GG04", "GG05")


def _rules(bill: Bill) -> list[dict]:
    return list(context_for(bill).version.rules)


def _rule_item_index(bill: Bill, rule: dict) -> int:
    label = re.search(r'item\("([^"]+)"', rule["actual"]).group(1)
    for i, x in enumerate(bill.line_items):
        if re.search(label, x.label, re.IGNORECASE):
            return i
    raise KeyError(label)


# clean bills --------------------------------------------------------------------------------


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_clean_electricity_bill_passes_every_fail_check(bill):
    r = results(bill)
    for check_id in MUST_PASS_ELECTRICITY:
        assert r[check_id].status == "pass", (check_id, r[check_id].note)
    for rule in _rules(bill):
        assert r[f"R:{rule['id']}"].status == "pass", rule["id"]
    assert [x.id for x in r.values() if x.status == "fail"] == []
    assert {x.status for x in r.values()} <= {"pass", "skip", "warn"}


@pytest.mark.parametrize("bill", GAS, ids=G_IDS)
def test_clean_gas_bill_passes_every_gas_check(bill):
    r = results(bill)
    for check_id in MUST_PASS_GAS:
        assert r[check_id].status == "pass", (check_id, r[check_id].note)
    assert [x.id for x in r.values() if x.status == "fail"] == []
    assert set(r) == set(MUST_PASS_GAS)  # no electricity check runs on a gas bill


def test_every_fail_check_has_a_planted_test_here():
    """The registry's fail-severity checks against the planted tests in this module."""
    planted = {
        name[len("test_planted_") :].split("_")[0].upper()
        for name in globals()
        if name.startswith("test_planted_")
    }
    # S01 and S02 (layout conformance) have their planted tests in test_checks_conformance.py
    fail_checks = {s.id for s in registered() if s.severity == "fail" and not s.id.startswith("S")}
    assert fail_checks <= planted, fail_checks - planted


# planted misreads ---------------------------------------------------------------------------


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g01_missing_net_payable(bill):
    assert results(with_totals(bill, net_payable=None))["G01"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g02_present_changed_by_one(bill):
    i = meter_index(bill, "kVAh", bill.meters[1].tod_slot)
    planted = with_meter(bill, i, present=bill.meters[i].present + 1)
    assert results(planted)["G02"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g03_leading_digit_of_slot_gross_units(bill):
    i = meter_index(bill, "kWh", bill.meters[0].tod_slot)
    planted = with_meter(bill, i, gross_units=leading_digit_changed(bill.meters[i].gross_units))
    assert results(planted)["G03"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY[:2], ids=E_IDS[:2])
def test_planted_g03_total_register_differs_from_energy_field(bill):
    """The total register proves energy.kwh: a misread there is caught too."""
    planted = with_section(bill, "energy", gross_kwh=leading_digit_changed(bill.energy.gross_kwh))
    assert results(planted)["G03"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY[:2], ids=E_IDS[:2])
def test_planted_g04_net_units_changed_by_two(bill):
    i = total_rows(bill)[0]
    row = bill.meters[i]
    with_oa = with_meter(bill, i, open_access_units=Decimal(1000), net_units=row.gross_units - 1000)
    assert results(with_oa)["G04"].status == "pass"
    planted = with_meter(with_oa, i, net_units=row.gross_units - 1000 + TWO)
    assert results(planted)["G04"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g05_amount_changed_by_two(bill):
    i = line_index(bill, "energy_charge")
    planted = with_line(bill, i, amount=bill.line_items[i].amount + TWO)
    assert results(planted)["G05"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY[:2], ids=E_IDS[:2])
def test_planted_g06_subtotal_changed_by_two(bill):
    items = tuple(
        x.model_copy(update={"group": "A"}) for x in bill.line_items if x.stage == "current"
    )
    sub = LineItem(
        index=len(items),
        group="A",
        label="Total (A)",
        kind="subtotal",
        amount=sum(x.amount for x in items),
    )
    grouped = bill.model_copy(update={"line_items": items + (sub,)})
    assert results(grouped)["G06"].status == "pass"
    planted = with_line(grouped, len(items), amount=sub.amount + TWO)
    assert results(planted)["G06"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g07_current_charges_changed_by_two(bill):
    assert (
        results(with_totals(bill, current_charges=bill.totals.current_charges + TWO))["G07"].status
        == "fail"
    )


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g08_arrears_changed_by_two(bill):
    assert (
        results(with_totals(bill, arrears_total=bill.totals.arrears_total + TWO))["G08"].status
        == "fail"
    )


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g09_net_payable_changed_by_two(bill):
    assert (
        results(with_totals(bill, net_payable=bill.totals.net_payable + TWO))["G09"].status
        == "fail"
    )


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g15_one_slot_changed(bill):
    i = meter_index(bill, "kVAh", bill.meters[0].tod_slot)
    planted = with_meter(bill, i, gross_units=leading_digit_changed(bill.meters[i].gross_units))
    assert results(planted)["G15"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g16_kvah_below_kwh(bill):
    mf = bill.meters[meter_index(bill, "kWh", None)].multiplying_factor
    tol = max(Decimal(1), Decimal("0.006") * mf)
    planted = with_section(bill, "energy", gross_kvah=bill.energy.gross_kwh - tol - 1)
    assert results(planted)["G16"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY[:2], ids=E_IDS[:2])
def test_planted_g17_billed_units_changed(bill):
    imp, exp = bill.energy.gross_kwh, Decimal(5000)
    nm = with_section(
        bill,
        "energy",
        net_metering_import_kwh=imp,
        net_metering_export_kwh=exp,
        billed_units=imp - exp,
    )
    assert results(nm)["G17"].status == "pass"
    planted = with_section(nm, "energy", billed_units=imp - exp + 100)
    assert results(planted)["G17"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g18_bill_month_shifted_by_three(bill):
    y, m = (int(x) for x in bill.period.bill_month.split("-"))
    m2 = m + 3
    shifted = f"{y + (m2 - 1) // 12}-{(m2 - 1) % 12 + 1:02d}"
    assert results(with_section(bill, "period", bill_month=shifted))["G18"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g19_dates_swapped(bill):
    swapped = with_section(
        bill, "period", reading_from=bill.period.reading_to, reading_to=bill.period.reading_from
    )
    assert results(swapped)["G19"].status == "fail"


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_g20_negative_amount_on_a_charge_line(bill):
    i = line_index(bill, "energy_charge")
    assert results(with_line(bill, i, amount=-bill.line_items[i].amount))["G20"].status == "fail"


@pytest.mark.parametrize("bill", GAS, ids=G_IDS)
def test_planted_gg01_missing_customer_id(bill):
    assert results(with_section(bill, "gas", customer_id=None))["GG01"].status == "fail"


@pytest.mark.parametrize("bill", GAS, ids=G_IDS)
def test_planted_gg02_leading_digit_of_current_reading(bill):
    planted = with_section(
        bill, "gas", reading_current=leading_digit_changed(bill.gas.reading_current)
    )
    assert results(planted)["GG02"].status == "fail"


@pytest.mark.parametrize("bill", GAS, ids=G_IDS)
def test_planted_gg03_leading_digit_of_mmbtu(bill):
    planted = with_section(bill, "gas", energy_mmbtu=leading_digit_changed(bill.gas.energy_mmbtu))
    assert results(planted)["GG03"].status == "fail"


@pytest.mark.parametrize("bill", GAS, ids=G_IDS)
def test_planted_gg04_amount_changed_by_two(bill):
    assert (
        results(with_line(bill, 0, amount=bill.line_items[0].amount + TWO))["GG04"].status == "fail"
    )


@pytest.mark.parametrize("bill", GAS, ids=G_IDS)
def test_planted_gg05_net_amount_changed_by_two(bill):
    assert (
        results(with_totals(bill, net_payable=bill.totals.net_payable + TWO))["GG05"].status
        == "fail"
    )


@pytest.mark.parametrize("bill", ELECTRICITY, ids=E_IDS)
def test_planted_r_each_profile_rule_catches_two_rupees_in_its_item(bill):
    for rule in _rules(bill):
        i = _rule_item_index(bill, rule)
        planted = with_line(bill, i, amount=bill.line_items[i].amount + TWO)
        r = results(planted)[f"R:{rule['id']}"]
        assert r.status == "fail", rule["id"]
        assert r.equality and f"line_items[{i}].amount" in r.proves


# inside the tolerance -----------------------------------------------------------------------


@pytest.mark.parametrize("bill", ELECTRICITY[:2], ids=E_IDS[:2])
def test_tolerances_inside_still_pass(bill):
    i = meter_index(bill, "kVAh", bill.meters[1].tod_slot)
    assert (
        results(with_meter(bill, i, difference=bill.meters[i].difference + Decimal("0.01")))[
            "G02"
        ].status
        == "pass"
    )
    mf = bill.meters[i].multiplying_factor
    g03_tol = max(Decimal(1), Decimal("0.006") * mf)
    assert (
        results(with_meter(bill, i, gross_units=bill.meters[i].gross_units + g03_tol))["G03"].status
        == "pass"
    )
    e = line_index(bill, "energy_charge")
    assert (
        results(with_line(bill, e, amount=bill.line_items[e].amount + Decimal("0.99")))[
            "G05"
        ].status
        == "pass"
    )
    n = len([x for x in bill.line_items if x.stage == "current"])
    g07_tol = max(Decimal(1), Decimal("0.01") * n)
    assert (
        results(with_totals(bill, current_charges=bill.totals.current_charges + g07_tol))[
            "G07"
        ].status
        == "pass"
    )
    assert (
        results(with_totals(bill, arrears_total=bill.totals.arrears_total + 1))["G08"].status
        == "pass"
    )
    assert (
        results(with_totals(bill, net_payable=bill.totals.net_payable + Decimal("0.99")))[
            "G09"
        ].status
        == "pass"
    )
    slots = len([r for r in bill.meters if r.quantity == "kVAh" and r.tod_slot])
    g15_tol = max(Decimal(1), Decimal("0.006") * mf * slots)
    t = meter_index(bill, "kVAh", None)
    assert (
        results(with_meter(bill, t, gross_units=bill.meters[t].gross_units + g15_tol))["G15"].status
        == "pass"
    )
    assert (
        results(with_section(bill, "energy", gross_kvah=bill.energy.gross_kwh - 1))["G16"].status
        == "pass"
    )
    for rule in _rules(bill):
        j = _rule_item_index(bill, rule)
        inside = with_line(bill, j, amount=bill.line_items[j].amount + Decimal("0.99"))
        assert results(inside)[f"R:{rule['id']}"].status == "pass", rule["id"]


def test_g05_profile_relative_tolerance():
    bill = ELECTRICITY[0]
    e = line_index(bill, "energy_charge")
    amount = bill.line_items[e].amount
    loosened = with_line(bill, e, amount=amount + Decimal("0.0004") * amount)
    assert results(loosened)["G05"].status == "fail"
    ctx = context_for(bill)
    ctx = CheckContext(version=ctx.version, tolerances=Tolerances(qty_x_rate_rel=Decimal("0.0005")))
    assert results(loosened, ctx)["G05"].status == "pass"


@pytest.mark.parametrize("bill", GAS[:2], ids=G_IDS[:2])
def test_gas_tolerances_inside_still_pass(bill):
    g = bill.gas
    assert (
        results(with_section(bill, "gas", volume_scm=g.volume_scm * Decimal("1.004")))[
            "GG02"
        ].status
        == "pass"
    )
    assert (
        results(with_section(bill, "gas", energy_mmbtu=g.energy_mmbtu * Decimal("1.004")))[
            "GG03"
        ].status
        == "pass"
    )
    assert (
        results(with_line(bill, 0, amount=bill.line_items[0].amount + Decimal("0.99")))[
            "GG04"
        ].status
        == "pass"
    )
    assert (
        results(with_totals(bill, net_payable=bill.totals.net_payable + Decimal("0.99")))[
            "GG05"
        ].status
        == "pass"
    )


# missing inputs skip ------------------------------------------------------------------------


def _blank_meters(bill: Bill, **changes) -> Bill:
    return bill.model_copy(
        update={"meters": tuple(r.model_copy(update=changes) for r in bill.meters)}
    )


def _blank_lines(bill: Bill, **changes) -> Bill:
    return bill.model_copy(
        update={"line_items": tuple(x.model_copy(update=changes) for x in bill.line_items)}
    )


def test_equality_checks_skip_when_inputs_are_missing():
    bill = ELECTRICITY[0]
    cases = {
        "G02": _blank_meters(bill, present=None),
        "G03": _blank_meters(bill, multiplying_factor=None),
        "G04": bill,  # the layout prints no open access
        "G05": _blank_lines(bill, quantity=None),
        "G06": bill,  # no subtotal line
        "G07": with_totals(bill, current_charges=None),
        "G08": with_totals(bill, arrears_total=None),
        "G09": with_totals(bill, net_payable=None),
        "G15": bill.model_copy(update={"meters": ()}),
        "G17": bill,  # no net metering
    }
    for check_id, planted in cases.items():
        assert results(planted)[check_id].status == "skip", check_id
    gas = GAS[0]
    gas_cases = {
        "GG02": with_section(gas, "gas", reading_previous=None),
        "GG03": with_section(gas, "gas", gcv_kcal_per_scm=None),
        "GG04": _blank_lines(gas, rate=None),
        "GG05": with_totals(gas, net_payable=None),
    }
    for check_id, planted in gas_cases.items():
        assert results(planted)[check_id].status == "skip", check_id


def test_rules_skip_when_the_item_or_param_is_missing():
    bill = ELECTRICITY[0]
    rule = _rules(bill)[0]
    i = _rule_item_index(bill, rule)
    without = bill.model_copy(
        update={"line_items": tuple(x for j, x in enumerate(bill.line_items) if j != i)}
    )
    r = results(without)[f"R:{rule['id']}"]
    assert r.status == "skip" and r.note == "item_not_found"
    ctx = context_for(bill)
    no_params = CheckContext(version=replace(ctx.version, params={}), tolerances=ctx.tolerances)
    r = results(bill, no_params)[f"R:{rule['id']}"]
    assert r.status == "skip" and r.note.startswith("param_missing:")


def test_skip_is_never_pass_for_an_empty_bill():
    for bill_type in ("electricity", "gas"):
        empty = Bill(bill_type=bill_type)
        for r in results(
            empty, context_for(ELECTRICITY[0]) if bill_type == "electricity" else None
        ).values():
            if r.equality:
                assert r.status == "skip", r.id


def test_meter_row_type_is_the_schema_one():
    assert all(isinstance(r, MeterRow) for b in clean_bills() for r in b.meters)


def test_planted_g21_a_digit_in_a_detail_line_or_its_parent_fails():
    """G21 has no synthetic layout with a details table, so its planted bill is built here."""
    lines = (
        LineItem(index=0, label="Energy Charges", amount=Decimal("5148057.81")),
        LineItem(
            index=1,
            label="TOD-1",
            kind="info",
            amount=Decimal("2000000.00"),
            detail_of="Energy Charges",
        ),
        LineItem(
            index=2,
            label="TOD-2",
            kind="info",
            amount=Decimal("3148057.81"),
            detail_of="Energy Charges",
        ),
    )
    clean = Bill(bill_type="electricity", line_items=lines)
    assert results(clean)["G21"].status == "pass"
    planted = Bill(
        bill_type="electricity",
        line_items=lines[:1]
        + (lines[1].model_copy(update={"amount": Decimal("3000000.00")}),)
        + lines[2:],
    )
    assert results(planted)["G21"].status == "fail"


def test_planted_g22_a_digit_in_consumption_open_access_or_grid_units_fails():
    """G22 has no synthetic open-access layout, so its planted bill is built here (the
    shape of a PVVNL open-access adjustment bill, made-up figures in kVAh)."""
    from billx.core.schema import Energy

    def bill(gross, oa, billed):
        return Bill(
            bill_type="electricity",
            energy=Energy(
                gross_kvah=Decimal(gross),
                open_access_re_kwh=Decimal(oa),
                open_access_unit="kVAh",
                billed_units=Decimal(billed),
                billed_unit="kVAh",
            ),
        )

    assert results(bill("1200000", "250000.250", "949999.750"))["G22"].status == "pass"
    for planted in (
        ("1700000", "250000.250", "949999.750"),
        ("1200000", "251000.250", "949999.750"),
        ("1200000", "250000.250", "950499.750"),
    ):
        assert results(bill(*planted))["G22"].status == "fail", planted
