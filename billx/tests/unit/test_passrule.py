"""The pass rule (5.2): passed means every required value verified and the arithmetic
covering money and energy; a failing check on verified inputs is a printed inconsistency."""

from billx.core.schema import CheckResult, Reading, make_value
from billx.reader.validate.passrule import verdict

REQUIRED = [
    "consumer.account_number",
    "period.from",
    "period.to",
    "period.bill_month",
    "energy.kwh",
    "totals.net_payable",
]


def _r(reader, raw, ft):
    from billx.core.normalize import normalise

    m = {"text_layer": "text_layer", "local_ocr": "ocr", "model_a": "vision"}[reader]
    fam = "openai" if reader == "model_a" else None
    return Reading(
        reader=reader, method=m, family=fam, raw=raw, normalised=normalise(raw, ft), page=0
    )


def _value(path, raw, ft="number", readers=("text_layer", "model_a"), checks=()):
    return make_value(path, ft, tuple(_r(r, raw, ft) for r in readers), checks=checks)


def _values(**overrides):
    base = {
        "consumer.account_number": ("994927801935", "identifier"),
        "period.from": ("01-04-2025", "date"),
        "period.to": ("30-04-2025", "date"),
        "period.bill_month": ("APR-2025", "month"),
        "energy.kwh": ("24,77,850.00", "number"),
        "totals.net_payable": ("2,43,58,156.60", "number"),
    }
    out = []
    for path, (raw, ft) in base.items():
        readers = overrides.get(path, ("text_layer", "model_a"))
        out.append(_value(path, raw, ft, readers))
    return out


def _check(id, status, proves=(), equality=True, unverified=()):
    return CheckResult(
        id=id,
        description=id,
        status=status,
        detects="x",
        proves=proves,
        equality=equality,
        unverified_inputs=unverified,
    )


GOOD_CHECKS = [
    _check("G03", "pass", ("energy.kwh",)),
    _check("G09", "pass", ("totals.current_charges", "totals.arrears", "totals.net_payable")),
]


def _verdict(values, checks):
    return verdict(
        values,
        checks,
        required=REQUIRED,
        energy_paths=("energy.kwh", "energy.kvah"),
        money_path="totals.net_payable",
        either_required={"energy.kwh": "energy.kvah"},
    )


def test_passes_when_everything_is_verified_and_covered():
    v = _verdict(_values(), GOOD_CHECKS)
    assert v.passed and v.status == "passed" and v.accepted and v.accepted_by == "engine"
    assert v.review_reasons == () and v.flags == ()


def test_an_unverified_required_field_needs_review():
    v = _verdict(_values(**{"energy.kwh": ("local_ocr",)}), GOOD_CHECKS)
    assert (
        not v.passed and v.status == "needs_review" and "unverified:energy.kwh" in v.review_reasons
    )
    assert not v.accepted


def test_missing_arithmetic_is_insufficient_arithmetic():
    v = _verdict(_values(), [_check("G09", "pass", ("totals.net_payable",))])
    assert v.review_reasons == ("insufficient_arithmetic",)
    v = _verdict(_values(), [_check("G01", "pass", (), equality=False)])
    assert "insufficient_arithmetic" in v.review_reasons


def test_a_failing_check_on_verified_inputs_is_a_printed_inconsistency_and_passes():
    checks = GOOD_CHECKS + [_check("G05", "fail", ("line_items[2].amount",))]
    v = _verdict(_values(), checks)
    assert v.passed and v.flags == ("printed_inconsistency:G05",) and v.failed_checks == ("G05",)


def test_a_printed_inconsistency_in_the_only_check_covering_the_money_still_counts():
    """G09 failing on verified inputs: the arithmetic tied net payable to its parts and the
    bill itself is wrong; that is coverage, not insufficient arithmetic."""
    checks = [
        _check("G03", "pass", ("energy.kwh",)),
        _check("G09", "fail", ("totals.current_charges", "totals.arrears", "totals.net_payable")),
    ]
    v = _verdict(_values(), checks)
    assert v.passed and v.flags == ("printed_inconsistency:G09",)
    assert "insufficient_arithmetic" not in v.review_reasons


def test_a_failing_check_with_an_unverified_input_needs_review():
    checks = GOOD_CHECKS + [
        _check("G05", "fail", ("line_items[2].amount",), unverified=("line_items[2].amount",))
    ]
    v = _verdict(_values(), checks)
    assert not v.passed
    assert (
        "check_failed:G05" in v.review_reasons
        and "unverified:line_items[2].amount" in v.review_reasons
    )


def test_a_skipped_check_because_of_an_unverified_value_needs_review():
    checks = GOOD_CHECKS + [_check("G06", "skip", unverified=("line_items[1].amount",))]
    v = _verdict(_values(), checks)
    assert not v.passed and "unverified:line_items[1].amount" in v.review_reasons


def test_kvah_satisfies_the_energy_requirement_under_1_1():
    values = [v for v in _values() if v.path != "energy.kwh"]
    values.append(_value("energy.kvah", "26,60,310.00"))
    checks = [_check("G03", "pass", ("energy.kvah",)), GOOD_CHECKS[1]]
    v = _verdict(values, checks)
    assert v.passed


def test_a_required_field_not_printed_is_named():
    values = [v for v in _values() if v.path != "totals.net_payable"]
    values.append(make_value("totals.net_payable", "number", ()))
    v = _verdict(values, GOOD_CHECKS)
    assert "required_field_not_printed:totals.net_payable" in v.review_reasons
