"""The generic checks beyond the planted misreads: the warnings G10 to G14, the date and
sign checks, and the default offsets without a profile."""

from __future__ import annotations

from decimal import Decimal

from _checks_support import clean_bills, context_for, results, with_line, with_section

from billx.core.schema import Bill, HistoryRow, LineItem, MeterRow
from billx.reader.validate.registry import CheckContext

BILL = [b for b in clean_bills() if b.bill_type == "electricity"][0]


def _one(bill: Bill, check_id: str, ctx: CheckContext | None = None):
    return results(bill, ctx)[check_id]


def test_g10_billing_demand():
    r = _one(BILL, "G10")
    assert r.status == "pass" and r.note is None
    with_min = with_section(BILL, "connection", minimum_billable_kva=BILL.demand.billing_kva + 100)
    assert _one(with_min, "G10").status == "warn"
    below = with_section(BILL, "demand", billing_kva=BILL.demand.recorded_kva - 500)
    assert _one(below, "G10").status == "warn"
    assert _one(with_section(BILL, "demand", billing_kva=None), "G10").status == "skip"
    one_pct = with_section(BILL, "demand", billing_kva=BILL.demand.billing_kva * Decimal("1.009"))
    assert _one(one_pct, "G10").status == "pass"


def test_g11_power_factor():
    e = BILL.energy
    pf = (e.gross_kwh / e.gross_kvah).quantize(Decimal("0.001"))
    assert _one(with_section(BILL, "energy", power_factor=pf), "G11").status == "pass"
    assert (
        _one(with_section(BILL, "energy", power_factor=pf + Decimal("0.01")), "G11").status
        == "warn"
    )
    assert _one(BILL, "G11").status == "skip"


def test_g12_dates_and_billing_days():
    assert _one(BILL, "G12").status == "pass"
    assert (
        _one(with_section(BILL, "period", due_date=BILL.period.bill_date), "G12").status == "warn"
    )
    days = with_section(BILL, "period", billing_days=30)
    assert _one(days, "G12").status in ("pass", "warn")
    assert _one(with_section(BILL, "period", billing_days=5), "G12").status == "warn"
    assert _one(with_section(BILL, "period", bill_date=None, due_date=None), "G12").status == "skip"


def test_g13_history_median():
    assert _one(BILL, "G13").status == "skip"
    units = BILL.energy.gross_kwh
    hist = tuple(
        HistoryRow(month=f"2025-0{i}", units=units * Decimal(k)) for i, k in enumerate((1, 1, 2), 1)
    )
    assert _one(BILL.model_copy(update={"history": hist}), "G13").status == "pass"
    far = tuple(HistoryRow(month=f"2025-0{i}", units=units * 5) for i in range(1, 4))
    assert _one(BILL.model_copy(update={"history": far}), "G13").status == "warn"


def test_g14_extraction_notes():
    assert _one(BILL, "G14").status == "pass"
    r = _one(BILL.model_copy(update={"extraction_notes": ("smudged",)}), "G14")
    assert r.status == "warn" and r.note == "notes:1" and "smudged" not in str(r)


def test_g15_without_tod_complete_only_warns():
    bad = BILL.model_copy(
        update={
            "meters": tuple(
                r.model_copy(update={"gross_units": r.gross_units + 1000}) if r.tod_slot else r
                for r in BILL.meters
            )
        }
    )
    assert _one(bad, "G15").status == "fail"  # the profile marks tod_complete
    r = _one(bad, "G15", CheckContext())
    assert r.status == "warn" and "tod_complete_not_declared" in r.note


def test_g16_skips_with_net_metering_or_missing_register():
    assert (
        _one(with_section(BILL, "energy", net_metering_import_kwh=Decimal(1)), "G16").status
        == "skip"
    )
    assert _one(with_section(BILL, "energy", gross_kvah=None), "G16").status == "skip"


def test_g18_default_offset_without_a_profile():
    p = BILL.period  # AVVNL: bill month = reading month
    assert _one(BILL, "G18", CheckContext()).status == "pass"
    y, m = (int(x) for x in p.bill_month.split("-"))
    nxt = f"{y + m // 12}-{m % 12 + 1:02d}"
    assert (
        _one(with_section(BILL, "period", bill_month=nxt), "G18", CheckContext()).status == "pass"
    )
    assert (
        _one(with_section(BILL, "period", bill_month=nxt), "G18").status == "fail"
    )  # AVVNL offset [0, 0]
    assert _one(with_section(BILL, "period", bill_month=None), "G18").status == "skip"


def test_g19_same_day_fails_and_missing_skips():
    assert (
        _one(with_section(BILL, "period", reading_to=BILL.period.reading_from), "G19").status
        == "fail"
    )
    assert _one(with_section(BILL, "period", reading_from=None), "G19").status == "skip"


def test_g20_credit_lines_and_signed_lines_may_be_negative():
    assert _one(BILL, "G20").status == "pass"  # the TOD rebate is negative and labelled rebate
    i = next(i for i, x in enumerate(BILL.line_items) if x.code == "fppca")
    negative = with_line(BILL, i, amount=-BILL.line_items[i].amount)
    assert _one(negative, "G20").status == "fail"
    assert _one(with_line(negative, i, signed=True), "G20").status == "pass"
    assert _one(with_line(negative, i, label="Fuel Surcharge Credit"), "G20").status == "pass"
    neg_meter = BILL.model_copy(
        update={"meters": (MeterRow(label="kWh", quantity="kWh", present=Decimal(-1)),)}
    )
    assert _one(neg_meter, "G20").status == "fail"


def test_g01_presence_names_the_missing_fields():
    r = _one(
        BILL.model_copy(
            update={"consumer": BILL.consumer.model_copy(update={"account_number": None})}
        ),
        "G01",
    )
    assert r.status == "fail" and r.note == "missing:consumer.account_number"
    sc = BILL.model_copy(
        update={
            "consumer": BILL.consumer.model_copy(
                update={"account_number": None, "service_connection_number": "SC1"}
            )
        }
    )
    assert _one(sc, "G01").status == "pass"


def test_g05_percent_rate_and_g06_groups():
    pct = LineItem(
        index=99,
        group="T",
        label="Tax @ 5%",
        quantity=Decimal(1000),
        rate=Decimal(5),
        rate_unit="%",
        amount=Decimal(50),
    )
    bill = BILL.model_copy(update={"line_items": BILL.line_items + (pct,)})
    assert _one(bill, "G05").status == "pass"
    assert (
        _one(with_line(bill, len(bill.line_items) - 1, amount=Decimal(53)), "G05").status == "fail"
    )


def test_g09_without_arrears_or_with_adjustments():
    r = _one(
        BILL.model_copy(
            update={
                "totals": BILL.totals.model_copy(
                    update={"arrears_total": None, "net_payable": BILL.totals.current_charges}
                )
            }
        ),
        "G09",
    )
    assert (
        r.status == "pass"
        and r.note == "arrears_not_printed"
        and "totals.arrears_total" not in r.proves
    )
    adj = BILL.model_copy(
        update={
            "totals": BILL.totals.model_copy(
                update={
                    "adjustments_total": Decimal(-10),
                    "net_payable": BILL.totals.net_payable - 10,
                }
            )
        }
    )
    r = _one(adj, "G09")
    assert r.status == "pass" and "totals.adjustments_total" in r.proves


def test_results_never_contain_floats():
    for bill in clean_bills():
        for r in results(bill, context_for(bill)).values():
            assert "float" not in repr(r)
