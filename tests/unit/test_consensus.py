"""Consensus (5.1, 5.3): readings from several readers become one Value through the rule."""

from billx.reader.read.consensus import (
    FieldSpec,
    RawRead,
    ReaderOutput,
    consensus_fields,
    item_value,
    match_items,
)

SPECS = [
    FieldSpec("totals.net_payable", "number", "INR", required=True),
    FieldSpec("period.bill_month", "month", required=True),
    FieldSpec("consumer.name", "text"),
]


def _text(fields, **kw):
    return ReaderOutput(
        "text_layer", "text_layer", fields={k: RawRead(v, 0) for k, v in fields.items()}, **kw
    )


def _ocr(fields, **kw):
    return ReaderOutput(
        "local_ocr", "ocr", fields={k: RawRead(v, 0) for k, v in fields.items()}, **kw
    )


def _model(name, family, fields, **kw):
    return ReaderOutput(
        name,
        "vision",
        family=family,
        model_id="m",
        prompt_version="v1",
        fields={k: RawRead(v) for k, v in fields.items()},
        **kw,
    )


def test_a_local_reader_and_a_model_agreeing_verify_a_field():
    values = consensus_fields(
        [
            _text({"totals.net_payable": "2,43,58,156.60", "period.bill_month": "APR-2025"}),
            _model(
                "model_a",
                "openai",
                {"totals.net_payable": "2,43,58,156.60", "period.bill_month": "APR 2025"},
            ),
        ],
        SPECS,
    )
    by = {v.path: v for v in values}
    assert by["totals.net_payable"].verification == "verified"
    assert by["totals.net_payable"].value == "24358156.6" and by["totals.net_payable"].unit == "INR"
    assert (
        by["period.bill_month"].verification == "verified"
        and by["period.bill_month"].value == "2025-04"
    )
    assert by["consumer.name"].verification == "unverified" and by["consumer.name"].value is None


def test_the_text_layer_and_ocr_alone_never_verify():
    """They find a field by the same label rule (proof rule 2)."""
    values = consensus_fields(
        [_text({"totals.net_payable": "1,000.00"}), _ocr({"totals.net_payable": "1,000.00"})],
        SPECS[:1],
    )
    assert values[0].verification == "unverified" and values[0].value == "1000"


def test_disagreement_is_disputed_and_a_third_family_settles_it():
    outs = [_text({"totals.net_payable": "1,000.00"}), _ocr({"totals.net_payable": "7,000.00"})]
    v = consensus_fields(outs, SPECS[:1])[0]
    assert v.verification == "disputed"
    outs.append(_model("model_b", "anthropic", {"totals.net_payable": "7000"}))
    v = consensus_fields(outs, SPECS[:1])[0]
    assert (
        v.verification == "verified" and v.value == "7000" and v.readers == ("local_ocr", "model_b")
    )


def test_array_items_match_on_their_key_and_compare_field_by_field():
    a = ReaderOutput(
        "text_layer",
        "text_layer",
        meters=[
            {"register": "kWh", "tod_slot": "Normal", "present": "56545.82", "past": "56082.94"},
            {"register": "kWh", "tod_slot": "Off Peak", "present": "19132.33", "past": "18436.06"},
        ],
    )
    b = ReaderOutput(
        "model_a",
        "vision",
        family="openai",
        meters=[
            {"register": "KWH", "tod_slot": "normal", "present": "56545.82", "past": "56082.94"},
            {"register": "kWh", "tod_slot": "Off Peak", "present": "19132.33", "past": "18436.00"},
        ],
    )
    matched = match_items([a, b], "meters", ("register", "tod_slot"))
    assert [k for k, _ in matched] == ["KWH | NORMAL", "KWH | OFF PEAK"]
    normal = dict(matched)["KWH | NORMAL"]
    v = item_value("readings[0].current", "number", normal["present"], "kWh")
    assert v.verification == "verified" and v.value == "56545.82"
    off = dict(matched)["KWH | OFF PEAK"]
    assert item_value("readings[1].previous", "number", off["past"]).verification == "disputed"


def test_an_item_only_one_reader_has_is_unverified():
    a = ReaderOutput(
        "text_layer", "text_layer", lines=[{"label": "Meter Rent", "amount": "1500.00"}]
    )
    b = ReaderOutput("local_ocr", "ocr", lines=[])
    matched = match_items([a, b], "lines", ("label",))
    v = item_value("elements[0].amount", "number", dict(matched)["METER RENT"]["amount"], "INR")
    assert v.verification == "unverified" and v.readers == ("text_layer",)


def test_a_merged_key_takes_the_spelling_most_readers_gave():
    ocr = ReaderOutput(
        "local_ocr", "ocr", meters=[{"register": "kVAh", "tod_slot": "Moming Peak", "present": "1"}]
    )
    a = ReaderOutput(
        "model_a",
        "vision",
        family="openai",
        meters=[{"register": "kVAh", "tod_slot": "Morning Peak", "present": "1"}],
    )
    b = ReaderOutput(
        "model_b",
        "vision",
        family="anthropic",
        meters=[{"register": "kVAh", "tod_slot": "Morning Peak", "present": "1"}],
    )
    matched = match_items([ocr, a, b], "meters", ("register", "tod_slot"))
    assert [k for k, _ in matched] == ["KVAH | MORNING PEAK"]
    assert len(dict(matched)["KVAH | MORNING PEAK"]["present"]) == 3


def test_a_tied_spelling_is_settled_by_the_other_rows():
    """OCR misreads one slot name on the kVAh row; the model reads it right; both read the
    kWh row right: the kWh rows decide."""
    ocr = ReaderOutput(
        "local_ocr",
        "ocr",
        meters=[
            {"register": "kWh", "tod_slot": "Morning Peak", "present": "1"},
            {"register": "kVAh", "tod_slot": "Moming Peak", "present": "2"},
        ],
    )
    a = ReaderOutput(
        "model_a",
        "vision",
        family="openai",
        meters=[
            {"register": "kWh", "tod_slot": "Morning Peak", "present": "1"},
            {"register": "kVAh", "tod_slot": "Morning Peak", "present": "2"},
        ],
    )
    matched = match_items([ocr, a], "meters", ("register", "tod_slot"))
    assert [k for k, _ in matched] == ["KWH | MORNING PEAK", "KVAH | MORNING PEAK"]
