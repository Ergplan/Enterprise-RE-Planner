"""The rule families' JSON Schemas (packages/rulebooks/schemas), loaded once with their $refs
resolved. `validate_row` is the only gate a rule row passes before it is written."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from ..core.settings import get_settings

FAMILIES = (
    "tod_slots",
    "tariff_schedule",
    "oa_charge",
    "settlement",
    "regulatory_limit",
    "ists_waiver",
    "net_metering",
)


class UnknownFamily(ValueError):
    pass


@lru_cache
def _registry() -> tuple[Registry, dict[str, dict[str, Any]]]:
    sdir = get_settings().schemas_dir
    schemas = {p.name: json.loads(p.read_text()) for p in sdir.glob("*.schema.json")}
    reg: Registry = Registry()
    for name, s in schemas.items():
        reg = reg.with_resource(name, Resource.from_contents(s))
    return reg, schemas


def family_schema(family: str) -> dict[str, Any]:
    if family not in FAMILIES:
        raise UnknownFamily(family)
    return _registry()[1][f"{family}.schema.json"]


def validator(family: str) -> Draft202012Validator:
    reg, _ = _registry()
    return Draft202012Validator(family_schema(family), registry=reg)


def validate_row(family: str, row: dict[str, Any]) -> list[str]:
    """Errors as readable strings ('body/energy_charge/base: ...'); empty when the row is valid."""
    out = []
    for e in sorted(validator(family).iter_errors(row), key=lambda e: list(e.path)):
        path = "/".join(str(p) for p in e.path) or "(row)"
        out.append(f"{path}: {e.message}")
    return out
