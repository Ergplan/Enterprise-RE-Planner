"""Gas checks beyond the planted misreads: the correction factor, the D9 constant, a per-cent
rate, and the bill type scoping."""

from __future__ import annotations

from decimal import Decimal

from _checks_support import gas_truths, results, with_section

from billx.core.schema import Bill, Gas, LineItem, Totals
from billx.platform.synth.to_bill import bill_from_truth
from billx.reader.validate.gas import KCAL_PER_MMBTU

GAS = bill_from_truth(gas_truths()[0])


def test_gg02_applies_the_printed_correction_factor():
    g = GAS.gas
    raw = g.reading_current - g.reading_previous
    corrected = with_section(
        GAS, "gas", correction_factor=Decimal("1.02"), volume_scm=raw * Decimal("1.02")
    )
    r = results(corrected)["GG02"]
    assert r.status == "pass" and r.note is None and "gas.correction_factor" in r.proves
    assert (
        results(with_section(GAS, "gas", correction_factor=Decimal("1.02")))["GG02"].status
        == "fail"
    )
    assert results(GAS)["GG02"].note == "correction_factor_not_printed"


def test_gg03_uses_d9_constant_within_half_a_percent():
    assert KCAL_PER_MMBTU == Decimal("251995.76")
    g = GAS.gas
    exact = g.volume_scm * g.gcv_kcal_per_scm / KCAL_PER_MMBTU
    assert (
        results(with_section(GAS, "gas", energy_mmbtu=exact.quantize(Decimal("0.001"))))[
            "GG03"
        ].status
        == "pass"
    )
    assert (
        results(with_section(GAS, "gas", energy_mmbtu=exact * Decimal("1.006")))["GG03"].status
        == "fail"
    )


def test_gg04_percent_rate_and_gg05_items_only():
    pct = LineItem(
        index=0,
        label="VAT @ 5%",
        quantity=Decimal(1000),
        rate=Decimal(5),
        rate_unit="%",
        amount=Decimal(50),
    )
    info = LineItem(index=1, label="memo", kind="info", amount=Decimal(999))
    bill = Bill(
        bill_type="gas",
        gas=Gas(customer_id="x"),
        line_items=(pct, info),
        totals=Totals(net_payable=Decimal(50)),
    )
    r = results(bill)
    assert r["GG04"].status == "pass" and r["GG05"].status == "pass"
    assert "line_items[1].amount" not in r["GG05"].proves


def test_gas_checks_do_not_run_on_electricity_and_vice_versa():
    assert not any(k.startswith("GG") for k in results(Bill(bill_type="electricity")))
    assert all(k.startswith("GG") for k in results(Bill(bill_type="gas")))
    r = results(Bill(bill_type="gas"))
    assert r["GG01"].status == "fail" and all(
        r[k].status == "skip" for k in ("GG02", "GG03", "GG04", "GG05")
    )
