"""JSON for the store: exact values only. A `Decimal` is written as its string, a float is
refused (invariant 4), keys are sorted so the same object gives the same text."""

from __future__ import annotations

import json
from decimal import Decimal


def _default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"the store does not keep a {type(value).__name__}")


def check_no_float(value: object, path: str = "value") -> None:
    """Raise `TypeError` naming the first float found anywhere inside `value`."""
    if isinstance(value, float):
        raise TypeError(f"{path} is a float; the store keeps exact values only")
    if isinstance(value, dict):
        for key, item in value.items():
            check_no_float(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for i, item in enumerate(value):
            check_no_float(item, f"{path}[{i}]")


def dumps_exact(value: object, path: str = "value") -> str:
    """One line of JSON with no float in it; `Decimal`s become strings."""
    check_no_float(value, path)
    return json.dumps(value, default=_default, sort_keys=True, separators=(",", ":"))
