"""The rules engine: the ast allow-list (refusals at check_version and at evaluation), the
helpers, Decimal arithmetic, and the CheckResult a rule produces."""

from __future__ import annotations

from decimal import Decimal

import pytest
from _checks_support import context_for, electricity_truths

from billx.core.schema import Bill, LineItem, MeterRow
from billx.platform.synth.to_bill import bill_from_truth
from billx.reader.identify.profiles import ProfileVersion, check_rule, check_version
from billx.reader.validate.expr import (
    ExpressionError,
    evaluate,
    referenced_params,
    validate_expression,
)
from billx.reader.validate.registry import CheckContext
from billx.reader.validate.rules import Helpers, evaluate_rule, run_rules

REFUSED = [
    "__import__('os').system('true')",
    "param('x').real",
    "param('x')[0]",
    "(lambda: 1)()",
    "unknown_name + 1",
    "field",  # a helper not called
    "open('x')",
    "[1, 2][0]",
    "{'a': 1}['a']",
    "1 if True else 2",
    "param('x') ** 2",
    "param('x') % 2",
    "param('x') // 2",
    "param('x') == 1",
    "'abc'",
    "param(**{'name': 'x'})",
    "f'{1}'",
    "(x := 1)",
    "",
]


def _bill() -> Bill:
    return Bill(
        bill_type="electricity",
        meters=(
            MeterRow(
                label="kVAh Normal", quantity="kVAh", tod_slot="Normal", gross_units=Decimal(100)
            ),
            MeterRow(label="kVAh Peak", quantity="kVAh", tod_slot="Peak", gross_units=Decimal(50)),
            MeterRow(label="kVAh Total", quantity="kVAh", gross_units=Decimal(150)),
            MeterRow(label="kWh Total", quantity="kWh", gross_units=Decimal(140)),
        ),
        line_items=(
            LineItem(index=0, group="A", label="Energy Charges", amount=Decimal("1000.50")),
            LineItem(index=1, group="A", label="Electricity Duty", amount=Decimal("60")),
            LineItem(
                index=2, group="A", label="Total (A)", kind="subtotal", amount=Decimal("1060.50")
            ),
            LineItem(index=3, group="B", label="FPPA Surcharge", amount=Decimal("10")),
            LineItem(index=4, group="B", label="Fuel Surcharge", amount=Decimal("5")),
            LineItem(index=5, group="B", label="Memo Duty", kind="info", amount=Decimal("1")),
        ),
    )


def _version(rules=(), params=None) -> ProfileVersion:
    from billx.reader.identify.profiles import profiles

    discom = profiles().discoms["avvnl"]
    return ProfileVersion(
        discom=discom,
        version="t",
        effective_from="2025-01",
        status="draft",
        params=params or {"ed_rate": Decimal("0.40"), "pct": Decimal("5")},
        rules=tuple(rules),
    )


def _rule(**kw) -> dict:
    base = {
        "id": "t.rule",
        "description": "test",
        "severity": "error",
        "tolerance": 1,
        "actual": 'item("Electricity Duty")',
        "expected": 'param("ed_rate") * meter("Total", quantity="kVAh")',
        "detects": "Rs 1",
    }
    base.update(kw)
    return base


# the allow-list -----------------------------------------------------------------------------


@pytest.mark.parametrize("text", REFUSED)
def test_refused_at_check_version_and_at_evaluation(text):
    errors = check_version({"status": "draft", "rules": [_rule(expected=text)]})
    assert any(e.startswith("rule 0: expected:") for e in errors), errors
    assert check_rule(_rule(actual=text))
    with pytest.raises(ExpressionError):
        validate_expression(text)
    with pytest.raises(ExpressionError):
        evaluate(text, Helpers(_bill(), {"x": Decimal(1)}).table())
    with pytest.raises(ExpressionError):
        evaluate_rule(
            _rule(expected=text), _bill(), CheckContext(version=_version(params={"x": Decimal(1)}))
        )


def test_allowed_constructs_pass_validation():
    for text in [
        "1 + 2 * (3 - 4) / 5",
        "-param('x') + +1",
        "abs(min(1, 2) - max(3, round(4.567, 2)))",
        'items_sum("FPP|Fuel", kind="item", stage="current") + subtotal("A")',
        'meters_sum("Peak", quantity="kVAh", attr="gross_units")',
        'field("energy.gross_kwh")',
    ]:
        validate_expression(text)


def test_referenced_params():
    assert referenced_params('param("a") * (param("b") + 1) + item("x")') == {"a", "b"}


# Decimal arithmetic and helpers -------------------------------------------------------------


def test_literals_are_exact_decimals():
    table = Helpers(_bill(), {}).table()
    assert evaluate("0.1 + 0.2", table) == Decimal("0.3")
    assert evaluate("1 / 8", table) == Decimal("0.125")
    assert isinstance(evaluate("7.30 * 3", table), Decimal)
    assert evaluate("round(2.345, 2)", table) == Decimal("2.34")  # half-even, as Python's round
    assert evaluate("abs(-3) + min(4, 2) + max(1, 9)", table) == Decimal(14)
    with pytest.raises(ExpressionError):
        evaluate("1 / 0", table)


def test_item_one_none_several():
    h = Helpers(_bill(), {})
    assert h.item("Electricity Duty") == Decimal(60)
    assert h.paths == ["line_items[1].amount"]
    from billx.reader.validate.rules import RuleSkip, RuleWarn

    with pytest.raises(RuleSkip):
        h.item("Nothing Here")
    with pytest.raises(RuleWarn):
        h.item("Surcharge")
    assert h.item("duty", kind="info") == Decimal(1)  # case-insensitive search, kind filter


def test_items_sum_subtotal_meter_and_field():
    h = Helpers(_bill(), {"ed_rate": Decimal("0.40")})
    assert h.items_sum("Surcharge") == Decimal(15)
    assert h.items_sum("Nothing") == Decimal(0)
    assert h.subtotal("A") == Decimal("1060.50")
    assert h.meter("Total", quantity="kVAh") == Decimal(150)
    assert h.meters_sum("Normal|Peak", quantity="kVAh") == Decimal(150)
    assert h.meters_sum("Total") == Decimal(290)
    assert h.param("ed_rate") == Decimal("0.40")
    bill = _bill().model_copy(
        update={"energy": _bill().energy.model_copy(update={"gross_kwh": Decimal(140)})}
    )
    assert Helpers(bill, {}).field("energy.gross_kwh") == Decimal(140)
    with pytest.raises(ExpressionError):
        Helpers(bill, {}).field("energy.__class__")
    with pytest.raises(ExpressionError):
        Helpers(bill, {}).field("line_items")
    with pytest.raises(ExpressionError):
        h.meter("Total", quantity="kVAh", attr="__dict__")
    assert set(h.paths) >= {
        "line_items[3].amount",
        "line_items[4].amount",
        "line_items[2].amount",
        "meters[2].gross_units",
    }


def test_rule_result_fields_and_proves():
    r = evaluate_rule(_rule(), _bill(), CheckContext(version=_version()))
    assert r.id == "R:t.rule" and r.status == "pass" and r.equality and r.detects == "Rs 1"
    assert r.expected == "60" and r.actual == "60" and r.tolerance == "1"
    assert set(r.proves) == {"line_items[1].amount", "meters[2].gross_units"}
    assert set(r.paths) == set(r.proves)


def test_rule_warning_severity_is_not_an_equality():
    r = evaluate_rule(
        _rule(severity="warning", expected='param("ed_rate") * 100'),
        _bill(),
        CheckContext(version=_version()),
    )
    assert r.status == "warn" and not r.equality and r.proves == ()


def test_rule_rel_tolerance():
    rule = _rule(expected="61", rel_tolerance=Decimal("0.02"))
    del rule["tolerance"]
    assert evaluate_rule(rule, _bill(), CheckContext(version=_version())).status == "pass"
    rule["rel_tolerance"] = Decimal("0.01")
    assert evaluate_rule(rule, _bill(), CheckContext(version=_version())).status == "fail"


def test_rule_ambiguous_item_warns_and_missing_skips():
    r = evaluate_rule(_rule(actual='item("Surcharge")'), _bill(), CheckContext(version=_version()))
    assert r.status == "warn" and r.note.startswith("item_ambiguous")
    r = evaluate_rule(_rule(actual='subtotal("Z")'), _bill(), CheckContext(version=_version()))
    assert r.status == "skip" and r.note == "subtotal_not_found"
    r = evaluate_rule(_rule(expected='meter("Nope")'), _bill(), CheckContext(version=_version()))
    assert r.status == "skip" and r.note == "meter_not_found"


def test_params_history_in_force_for_the_bill_month():
    from dataclasses import replace

    v = replace(
        _version(), params_history=({"from": "2025-04", "params": {"ed_rate": Decimal("0.50")}},)
    )
    assert CheckContext.for_version(v, "2025-03").params()["ed_rate"] == Decimal("0.40")
    assert CheckContext.for_version(v, "2025-04").params()["ed_rate"] == Decimal("0.50")


def test_run_rules_on_the_synthetic_profiles():
    bill = bill_from_truth(electricity_truths()[0])
    ctx = context_for(bill)
    out = run_rules(bill, ctx)
    assert [r.id for r in out] == [f"R:{r['id']}" for r in ctx.version.rules]
    assert all(r.status == "pass" and r.proves for r in out)
    assert run_rules(bill, CheckContext()) == []
