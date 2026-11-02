"""Layout conformance S01 to S06, with the planted tests for S01 and S02 (severity fail)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from _checks_support import clean_bills, context_for, results

from billx.core.schema import LineItem
from billx.reader.validate.registry import CheckContext

BILL = [b for b in clean_bills() if b.discom.name_as_printed == "AVVNL"][0]
TEMPLATE = {
    "required_fields": [
        "consumer.account_number",
        "period.bill_month",
        "totals.net_payable",
        "energy.gross_kvah",
    ],
    "line_items": [
        {
            "label_pattern": "energy charges",
            "code": "energy_charge",
            "kind": "item",
            "stage": "current",
            "required": True,
        },
        {"label_pattern": "fixed charges", "required": True},
        {"label_pattern": "tod (surcharge|rebate)"},
        {"label_pattern": "fuel surcharge"},
        {"label_pattern": "electricity duty", "required": True},
        {"label_pattern": "cess"},
        {"label_pattern": "meter rent"},
        {"label_pattern": "arrears", "kind": "item", "stage": "arrear"},
    ],
    "meters": [
        {"label_pattern": "total", "quantity": "kVAh"},
        {"label_pattern": "total", "quantity": "kWh"},
        {"label_pattern": "peak|normal"},
    ],
    "drift_threshold": 3,
}


def _ctx(template=TEMPLATE) -> CheckContext:
    base = context_for(BILL)
    return CheckContext(
        version=replace(base.version, template=template), tolerances=base.tolerances
    )


def test_clean_bill_conforms():
    r = results(BILL, _ctx())
    assert all(r[f"S{i:02d}"].status == "pass" for i in range(1, 7)), {
        k: v.status for k, v in r.items() if k.startswith("S")
    }


def test_no_template_runs_no_s_checks():
    assert not any(k.startswith("S") for k in results(BILL))


def test_planted_s01_required_field_missing():
    r = results(
        BILL.model_copy(update={"energy": BILL.energy.model_copy(update={"gross_kvah": None})}),
        _ctx(),
    )
    assert r["S01"].status == "fail" and r["S01"].note == "missing:energy.gross_kvah"
    assert r["S06"].status == "pass"


def test_planted_s02_required_line_missing():
    without = BILL.model_copy(
        update={"line_items": tuple(x for x in BILL.line_items if x.code != "electricity_duty")}
    )
    r = results(without, _ctx())
    assert r["S02"].status == "fail" and r["S02"].note == "missing_required:1"


def test_s03_s04_s05_warn():
    extra = LineItem(index=99, label="Mystery Levy", amount=Decimal(1))
    r = results(BILL.model_copy(update={"line_items": BILL.line_items + (extra,)}), _ctx())
    assert r["S03"].status == "warn" and r["S03"].paths == (
        f"line_items[{len(BILL.line_items)}].amount",
    )
    r = results(BILL.model_copy(update={"meters": BILL.meters[:-1]}), _ctx())
    assert r["S04"].status == "warn" and r["S04"].note.startswith("missing:1")
    i = next(i for i, x in enumerate(BILL.line_items) if x.code == "energy_charge")
    r = results(
        BILL.model_copy(
            update={
                "line_items": tuple(
                    x.model_copy(update={"stage": "arrear"}) if j == i else x
                    for j, x in enumerate(BILL.line_items)
                )
            }
        ),
        _ctx(),
    )
    assert r["S05"].status == "warn" and r["S05"].paths == (f"line_items[{i}].kind",)


def test_drift_downgrades_s01_and_s02_and_flags_s06():
    bill = BILL.model_copy(
        update={
            "line_items": tuple(
                x for x in BILL.line_items if x.code not in ("electricity_duty", "energy_charge")
            )
            + (
                LineItem(index=97, label="New Levy A", amount=Decimal(1)),
                LineItem(index=98, label="New Levy B", amount=Decimal(2)),
            ),
            "energy": BILL.energy.model_copy(update={"gross_kvah": None}),
        }
    )
    r = results(bill, _ctx())
    assert r["S01"].status == "warn" and r["S02"].status == "warn"
    assert (
        r["S06"].status == "warn" and r["S06"].note == "layout_drift" and int(r["S06"].actual) >= 3
    )
    r = results(bill, _ctx({**TEMPLATE, "drift_threshold": 10}))
    assert r["S01"].status == "fail" and r["S02"].status == "fail" and r["S06"].status == "pass"


def test_template_without_meters_skips_s04():
    assert (
        results(BILL, _ctx({k: v for k, v in TEMPLATE.items() if k != "meters"}))["S04"].status
        == "skip"
    )
