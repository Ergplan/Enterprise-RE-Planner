"""The formula recheck per element, run_checks, and the registry's own invariants: every
check declares detects, every equality check declares proves, and every result is strings
and Decimals only."""

from __future__ import annotations

from decimal import Decimal

from _checks_support import clean_bills, context_for, enriched_bills, results

from billx.core.schema import Bill, LineItem
from billx.reader.validate.formula import recheck_all, recheck_element, run_checks, specs_for
from billx.reader.validate.registry import CheckContext, Tolerances, registered, spec

EXPECTED_IDS = (
    [f"G{i:02d}" for i in range(1, 23)]
    + [f"GG{i:02d}" for i in range(1, 6)]
    + [f"S{i:02d}" for i in range(1, 7)]
    + [f"T{i:02d}" for i in range(1, 6)]
)


def _line(**kw) -> LineItem:
    base = {"index": 0, "label": "Energy Charges", "amount": Decimal("730")}
    base.update(kw)
    return LineItem(**base)


def _breakdown_bill() -> Bill:
    """A bill whose calculation table itemises its energy charge (G21's input)."""
    return Bill(
        bill_type="electricity",
        line_items=(
            _line(index=0, label="Energy Charges", amount=Decimal("730")),
            _line(
                index=1,
                label="TOD-1",
                kind="info",
                amount=Decimal("330"),
                detail_of="Energy Charges",
            ),
            _line(
                index=2,
                label="TOD-2",
                kind="info",
                amount=Decimal("400"),
                detail_of="Energy Charges",
            ),
        ),
    )


def test_registry_ids_and_order():
    assert [s.id for s in registered()] == EXPECTED_IDS


def test_every_registered_check_declares_detects_and_equality_checks_declare_proves():
    bills = clean_bills() + enriched_bills() + [_breakdown_bill()]
    for s in registered():
        assert s.detects.strip(), s.id
        assert s.severity in ("fail", "warn")
        if s.equality:
            declared = [s.declared_proves(b) for b in bills if s.applies(b.bill_type)]
            assert any(declared), s.id
    equality = {s.id for s in registered() if s.equality}
    assert equality == {
        "G02",
        "G03",
        "G04",
        "G05",
        "G06",
        "G07",
        "G08",
        "G09",
        "G15",
        "G17",
        "G21",
        "G22",
        "GG02",
        "GG03",
        "GG04",
        "GG05",
    }


def test_every_result_carries_detects_and_passing_equality_results_prove_paths():
    for bill in clean_bills() + enriched_bills():
        for r in results(bill).values():
            assert r.detects, r.id
            if r.equality and r.status == "pass":
                assert r.proves, r.id
                assert set(r.proves) <= set(r.paths)
            if not r.equality:
                assert r.proves == ()
            assert r.unverified_inputs == ()
            for v in (r.expected, r.actual, r.tolerance):
                assert v is None or isinstance(v, str)


def test_contract_paths_sit_beside_schema_paths():
    bill = clean_bills()[0]
    r = results(bill)
    assert {
        "totals.net_payable",
        "totals.arrears_total",
        "totals.arrears",
        "totals.current_charges",
    } <= set(r["G09"].proves)
    assert {"energy.gross_kwh", "energy.kwh", "energy.gross_kvah", "energy.kvah"} <= set(
        r["G15"].proves
    )
    assert "energy.kwh" in r["G03"].proves
    gas = [b for b in clean_bills() if b.bill_type == "gas"][0]
    g = results(gas)
    assert {"gas.volume_scm", "volume.scm", "energy.mmbtu", "gas.gcv_kcal_per_scm"} <= set(
        g["GG03"].proves
    )
    assert {"totals.net_payable", "totals.amount"} <= set(g["GG05"].proves)
    assert {"readings.previous", "readings.current"} <= set(g["GG02"].proves)


def test_run_checks_order_and_scope():
    bill = clean_bills()[0]
    ids = [r.id for r in run_checks(bill, context_for(bill))]
    g = [i for i in ids if i.startswith("G") and not i.startswith("GG")]
    assert g == [f"G{i:02d}" for i in range(1, 23)]
    assert not any(i.startswith("GG") for i in ids)
    assert not any(i.startswith("S") for i in ids)  # the draft version has no template
    assert [i for i in ids if i.startswith("T")] == [f"T{i:02d}" for i in range(1, 6)]
    assert ids.index("R:avvnl.electricity_duty") > ids.index("T05")
    no_profile = [r.id for r in run_checks(bill)]
    assert not any(i.startswith(("T", "R:", "S")) for i in no_profile)
    assert [s.id for s in specs_for(bill, CheckContext())] == no_profile


def test_recheck_element():
    ctx = CheckContext()
    r = recheck_element(
        _line(quantity=Decimal(100), rate=Decimal("7.30")), Bill(bill_type="electricity"), ctx
    )
    assert (r.status, r.computed, r.billed, r.difference, r.formula) == (
        "match",
        "730",
        "730",
        "0",
        "quantity x rate",
    )
    r = recheck_element(
        _line(quantity=Decimal(100), rate=Decimal("7.30"), amount=Decimal("732")),
        Bill(bill_type="electricity"),
        ctx,
    )
    assert r.status == "differs" and r.difference == "2"
    r = recheck_element(
        _line(quantity=Decimal(1000), rate=Decimal(5), rate_unit="%", amount=Decimal(50)),
        Bill(bill_type="electricity"),
        ctx,
    )
    assert r.status == "match" and r.formula == "quantity x rate / 100"
    r = recheck_element(
        _line(quantity=Decimal(100), rate=Decimal("-0.73"), amount=Decimal("-73")),
        Bill(bill_type="electricity"),
        ctx,
    )
    assert r.status == "match"
    assert (
        recheck_element(_line(), Bill(bill_type="electricity"), ctx).reason == "no_quantity_or_rate"
    )
    assert (
        recheck_element(_line(kind="info"), Bill(bill_type="electricity"), ctx).reason
        == "info_line"
    )
    assert (
        recheck_element(_line(kind="subtotal"), Bill(bill_type="electricity"), ctx).reason
        == "subtotal"
    )
    loose = CheckContext(tolerances=Tolerances(qty_x_rate_rel=Decimal("0.01")))
    r = recheck_element(
        _line(quantity=Decimal(100), rate=Decimal("7.30"), amount=Decimal("735")),
        Bill(bill_type="electricity"),
        loose,
    )
    assert r.status == "match"


def test_recheck_all_on_synthetic_bills():
    for bill in clean_bills():
        out = recheck_all(bill, context_for(bill))
        assert len(out) == len(bill.line_items)
        for x, r in zip(bill.line_items, out, strict=True):
            if x.quantity is not None and x.rate is not None:
                assert r.status == "match", x.label
            else:
                assert r.status == "not_computable"


def test_spec_lookup():
    assert spec("G09").equality and spec("G09").severity == "fail"
    assert spec("T01").severity == "warn" and not spec("T01").equality
    assert spec("GG02").applies_to == "gas" and spec("S01").applies_to == "both"
