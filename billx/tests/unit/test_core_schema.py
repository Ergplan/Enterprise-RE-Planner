"""Core schema 2.0: strict Decimals, frozen results, and verdicts only from the rule."""

import inspect
import types
import typing
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from billx.core import schema
from billx.core.normalize import normalise
from billx.core.schema import (
    ALL_MODELS,
    Bill,
    LineItem,
    Reading,
    Value,
    make_value,
    with_checks,
)


def reading(reader, raw, field_type="number", **kw):
    methods = {
        "text_layer": "text_layer",
        "local_ocr": "ocr",
        "model_a": "vision",
        "model_b": "vision",
        "human": "human",
    }
    fam = {"model_a": "openai", "model_b": "anthropic"}.get(reader)
    return Reading(
        reader=reader,
        method=methods[reader],
        family=fam,
        raw=raw,
        normalised=normalise(raw, field_type),
        **kw,
    )


def test_no_float_anywhere_in_the_schema():
    """Rule 7: every numeric field is Decimal (or int for counts); a float annotation
    anywhere in a result model is a failure."""
    for model in ALL_MODELS:
        for name, field in model.model_fields.items():
            for t in _leaf_types(field.annotation):
                assert t is not float, f"{model.__name__}.{name} is a float"


def _leaf_types(annotation):
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType, tuple, list, dict, typing.Literal):
        for arg in typing.get_args(annotation):
            yield from _leaf_types(arg)
    elif inspect.isclass(annotation):
        yield annotation


def test_strict_rejects_float_and_string_coercion():
    with pytest.raises(ValidationError):
        LineItem(index=0, label="a", amount=1.5)
    with pytest.raises(ValidationError):
        LineItem(index=0, label="a", amount="1.50")
    assert LineItem(index=0, label="a", amount=Decimal("1.50")).amount == Decimal("1.50")


def test_extra_keys_are_refused_and_results_are_frozen():
    with pytest.raises(ValidationError):
        Bill(bill_type="electricity", colour="blue")
    item = LineItem(index=0, label="a", amount=Decimal(1))
    with pytest.raises(ValidationError):
        item.amount = Decimal(2)


def test_a_value_carries_exactly_the_rules_decision():
    v = make_value(
        "totals.net_payable",
        "number",
        (reading("text_layer", "2,43,58,156.60"), reading("model_a", "2,43,58,156.60")),
        unit="INR",
    )
    assert v.verification == "verified" and v.value == "24358156.6"
    assert v.printed == "2,43,58,156.60" and v.proof == ("consensus",) and v.source == "ocr"


def test_a_hand_marked_verification_is_rejected():
    with pytest.raises(ValidationError, match="not decided by the rule"):
        Value(path="x", field_type="number", value="1", verification="verified")
    r = reading("local_ocr", "1")
    with pytest.raises(ValidationError):
        Value(
            path="x",
            field_type="number",
            value="1",
            readings=(r,),
            readers=("local_ocr",),
            proof=("single",),
            source="ocr",
            verification="verified",
        )


def test_with_checks_adds_arithmetic_through_the_rule():
    v = make_value("x", "number", (reading("text_layer", "10"), reading("model_a", "10")))
    v2 = with_checks(v, ("G09",))
    assert v2.proof == ("consensus", "arithmetic") and v2.checks == ("G09",)
    single = with_checks(make_value("x", "number", (reading("local_ocr", "10"),)), ("G09",))
    assert single.verification == "unverified"


def test_every_model_is_strict_and_listed():
    listed = set(ALL_MODELS)
    for name, obj in vars(schema).items():
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and obj not in (BaseModel, schema.Strict)
        ):
            assert obj in listed, f"{name} is not in ALL_MODELS"
            assert obj.model_config.get("strict") and obj.model_config.get("extra") == "forbid"
