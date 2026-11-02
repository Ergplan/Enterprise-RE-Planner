"""T01 to T05 on hand-built bills: warnings only, skip without a param or an input. The
synthetic energy and demand rates still vary until package D fixes them, so nothing here
depends on a generated bill's rates."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from _checks_support import context_for, electricity_truths

from billx.core.schema import Bill, Demand, Energy, LineItem
from billx.platform.synth.to_bill import bill_from_truth
from billx.reader.validate.formula import run_checks
from billx.reader.validate.registry import CheckContext

AVVNL = bill_from_truth(next(t for t in electricity_truths() if t["layout"] == "avvnl-ht-synth-v1"))
PVVNL = bill_from_truth(
    next(t for t in electricity_truths() if t["layout"] == "pvvnl-hv2-synth-v1")
)


def _line(i, label, code, qty, rate, unit="kVAh", **kw) -> LineItem:
    return LineItem(
        index=i,
        label=label,
        code=code,
        quantity=Decimal(qty),
        rate=Decimal(rate),
        unit=unit,
        amount=Decimal(qty) * Decimal(rate),
        **kw,
    )


def _bill(lines, **sections) -> Bill:
    return Bill(bill_type="electricity", line_items=tuple(lines), **sections)


def _t(bill: Bill, ctx: CheckContext) -> dict:
    return {r.id: r for r in run_checks(bill, ctx) if r.id.startswith("T")}


def _ctx(base: Bill, **params) -> CheckContext:
    c = context_for(base)
    v = replace(
        c.version, params={**c.version.params, **{k: Decimal(str(x)) for k, x in params.items()}}
    )
    return CheckContext(version=v, tolerances=c.tolerances)


def test_t01_energy_and_tod_rates():
    ctx = _ctx(AVVNL)
    good = _bill(
        [
            _line(0, "Energy Charges", "energy_charge", 100, "7.30"),
            _line(1, "TOD Surcharge", "tod_surcharge", 10, "0.73"),
            _line(2, "TOD Rebate", "tod_rebate", 10, "-0.73"),
        ]
    )
    r = _t(good, ctx)["T01"]
    assert (
        r.status == "pass"
        and r.note == "params:energy_rate_kvah,tod_surcharge_rate,tod_rebate_rate"
    )
    bad = _bill([_line(0, "Energy Charges", "energy_charge", 100, "7.15")])
    r = _t(bad, ctx)["T01"]
    assert (
        r.status == "warn"
        and r.expected == "7.3"
        and r.actual == "7.15"
        and r.paths == ("line_items[0].rate",)
    )
    assert (
        _t(_bill([_line(0, "Energy Charges", "energy_charge", 100, "6.00", unit="kWh")]), ctx)[
            "T01"
        ].status
        == "skip"
    )
    assert _t(_bill([]), ctx)["T01"].status == "skip"
    assert not any(k.startswith("T") for k in {r.id for r in run_checks(good, CheckContext())})


def test_t02_demand_charge():
    ctx = _ctx(PVVNL)
    line = _line(0, "Demand Charge", "demand_charge", 3000, "300.00", unit="kVA")
    assert _t(_bill([line], demand=Demand(billing_kva=Decimal(3000))), ctx)["T02"].status == "pass"
    assert _t(_bill([line]), ctx)["T02"].status == "pass"  # billing demand from the line's quantity
    r = _t(_bill([line], demand=Demand(billing_kva=Decimal(3100))), ctx)["T02"]
    assert r.status == "warn" and r.expected == "930000" and r.actual == "900000"
    assert (
        _t(_bill([line.model_copy(update={"rate": Decimal("290")})]), ctx)["T02"].status == "warn"
    )
    assert _t(_bill([line]), _ctx(AVVNL))["T02"].status == "skip"  # AVVNL has no demand_rate_kva
    assert _t(_bill([line.model_copy(update={"quantity": None})]), ctx)["T02"].status == "skip"


def test_t03_duty_and_cess():
    ctx = _ctx(AVVNL)
    lines = [
        _line(0, "Electricity Duty", "electricity_duty", 100, "0.40"),
        _line(1, "Water Conservation Cess", "cess", 100, "0.10"),
        _line(2, "Urban Cess", "cess", 100, "0.15"),
    ]
    r = _t(_bill(lines), ctx)["T03"]
    assert r.status == "pass" and set(r.paths) == {
        "line_items[0].rate",
        "line_items[1].rate",
        "line_items[2].rate",
    }
    r = _t(_bill([lines[0], lines[1].model_copy(update={"rate": Decimal("0.12")}), lines[2]]), ctx)[
        "T03"
    ]
    assert r.status == "warn" and r.note.startswith("differs_from:water_cess_rate")
    pct = _line(0, "Electricity Duty", "electricity_duty", 1000, "5", rate_unit="%")
    assert _t(_bill([pct]), _ctx(AVVNL, ed_pct=5))["T03"].status == "pass"
    assert _t(_bill([pct]), ctx)["T03"].status == "skip"
    generic = _ctx(PVVNL, cess_rate="0.20")
    assert _t(_bill([_line(0, "Any Cess", "cess", 100, "0.20")]), generic)["T03"].status == "pass"


def test_t04_pf_band():
    ctx = _ctx(AVVNL, pf_incentive_min_pf="0.95", pf_penalty_max_pf="0.90")
    inc = LineItem(index=0, label="PF Incentive", code="pf_incentive", amount=Decimal(-100))
    pen = LineItem(index=0, label="PF Penalty", code="pf_penalty", amount=Decimal(100))
    assert (
        _t(_bill([inc], energy=Energy(power_factor=Decimal("0.97"))), ctx)["T04"].status == "pass"
    )
    assert (
        _t(_bill([inc], energy=Energy(power_factor=Decimal("0.93"))), ctx)["T04"].status == "warn"
    )
    assert (
        _t(_bill([pen], energy=Energy(power_factor=Decimal("0.88"))), ctx)["T04"].status == "pass"
    )
    assert (
        _t(_bill([pen], energy=Energy(power_factor=Decimal("0.93"))), ctx)["T04"].status == "warn"
    )
    assert _t(_bill([pen]), ctx)["T04"].status == "skip"
    assert (
        _t(_bill([pen], energy=Energy(power_factor=Decimal("0.93"))), _ctx(AVVNL))["T04"].status
        == "skip"
    )


def test_t05_fixed_charge():
    ctx = _ctx(AVVNL)
    fixed = _line(
        0, "Fixed Charges (on Billing Demand)", "demand_charge", 5000, "330.00", unit="kVA"
    )
    assert _t(_bill([fixed]), ctx)["T05"].status == "pass"
    r = _t(_bill([fixed.model_copy(update={"rate": Decimal("300.00")})]), ctx)["T05"]
    assert r.status == "warn" and r.expected == "330" and r.actual == "300"
    flat = LineItem(index=0, label="Minimum Charge", code="fixed_charge", amount=Decimal(1500))
    assert _t(_bill([flat]), _ctx(PVVNL, fixed_charge=1500))["T05"].status == "pass"
    assert _t(_bill([flat]), _ctx(PVVNL, fixed_charge=1600))["T05"].status == "warn"
    assert _t(_bill([flat]), _ctx(PVVNL))["T05"].status == "skip"
    assert _t(_bill([]), ctx)["T05"].status == "skip"


def test_t_checks_are_never_failures_and_never_equalities():
    from billx.reader.validate.registry import registered

    for s in registered():
        if s.id.startswith("T"):
            assert s.severity == "warn" and not s.equality
