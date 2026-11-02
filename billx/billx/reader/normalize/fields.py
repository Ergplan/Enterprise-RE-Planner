"""From Values to the transcription and back: the contract's guaranteed fields are produced
from `Bill` through the field map in profiles/_common.yaml (Developer Guide section 5), and
the engine builds `Bill` (`data`) from the consensus Values the same way, in reverse.

Nothing here decides a value: every Decimal written into `Bill` is a Value's `value`, which
decide() chose from the readings.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from billx.core.schema import (
    Bill,
    BillType,
    LineItem,
    MeterRow,
    Value,
)

_COMMON = Path(__file__).resolve().parents[3] / "profiles" / "_common.yaml"
_CONFIG = Path(__file__).resolve().parents[3] / "config" / "guaranteed_fields.yaml"


@lru_cache(maxsize=1)
def field_map() -> dict[str, str]:
    return dict(yaml.safe_load(_COMMON.read_text(encoding="utf-8"))["field_map"])


@lru_cache(maxsize=1)
def guaranteed_fields() -> dict[str, list[dict]]:
    return yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))


def scalar_specs(bill_type: BillType, contract: str = "1.1") -> list[dict]:
    """The scalar guaranteed fields for a bill type; contract "1.0" leaves out the 6.4 additions."""
    out = []
    for f in guaranteed_fields()[bill_type]:
        if f["type"] == "array":
            continue
        if contract == "1.0" and f.get("contract") == "1.1":
            continue
        out.append(f)
    return out


def required_paths(bill_type: BillType) -> list[str]:
    return [f["path"] for f in guaranteed_fields()[bill_type] if f.get("required")]


def either_required(bill_type: BillType) -> dict[str, str]:
    return {f["path"]: f["or"] for f in guaranteed_fields()[bill_type] if f.get("or")}


def data_value(v: Value) -> str | None:
    """The value a field contributes to the transcription the checks run on (5.2, condition
    4): a verified or confirmed value as decided; otherwise Model A's reading, the fullest
    transcription of the bill, when it read the field; otherwise the decided value. This
    never changes the field's own value or verdict, only which reading the arithmetic sees
    while the field is still unverified."""
    if v.verification in ("verified", "confirmed"):
        return v.value
    model_a = next((r for r in v.readings if r.reader == "model_a" and r.normalised), None)
    return model_a.normalised if model_a is not None else v.value


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _set(tree: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = tree
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def bill_from_values(
    bill_type: BillType,
    values: list[Value],
    meters: list[dict[str, Value | str | None]],
    lines: list[dict[str, Value | str | None]],
    *,
    extraction_notes: tuple[str, ...] = (),
) -> Bill:
    """The engine's transcription from the decided Values.

    `meters` rows carry Values for present/past/difference/multiplying_factor/consumption/
    open_access/net
    and strings for register and tod_slot; `lines` carry a Value for amount (and for
    quantity and rate when printed), strings for label, group, unit, kind, stage, code.
    """
    tree: dict[str, Any] = {"bill_type": bill_type}
    fmap = field_map()
    decimal_types = {"number"}
    specs = {f["path"]: f for f in scalar_specs(bill_type)}
    for v in values:
        target = fmap.get(v.path)
        value = data_value(v)
        if target is None or "[" in target or value is None:
            continue
        spec = specs.get(v.path)
        if spec and spec["type"] in decimal_types:
            d = _decimal(value)
            if d is None:
                continue
            _set(tree, target, d)
        else:
            _set(tree, target, value)

    # the unit a billed or open-access figure is printed in (G22 compares like with like)
    by_path = {v.path: v for v in values}
    for path, target in (
        ("energy.billed_units", "billed_unit"),
        ("open_access.re_kwh", "open_access_unit"),
        ("open_access.non_re_kwh", "open_access_unit"),
        ("open_access.banked_kwh", "open_access_unit"),
    ):
        v = by_path.get(path)
        if v is not None and data_value(v) is not None and v.unit in ("kWh", "kVAh"):
            tree.setdefault("energy", {})[target] = v.unit

    def val(x: Value | str | None) -> str | None:
        if isinstance(x, Value):
            return data_value(x)
        return x

    meter_rows = []
    for m in meters:
        register = (val(m.get("register")) or "other").strip()
        quantity = {"KWH": "kWh", "KVAH": "kVAh", "KVA": "kVA", "KW": "kW", "KVARH": "kVArh"}.get(
            register.upper(), "other"
        )
        slot = val(m.get("tod_slot"))
        if slot is not None and slot.strip().upper() in ("TOTAL", "ALL", "SUM"):
            slot = None  # the register's total row carries no slot (the checks rely on it)
        meter_rows.append(
            MeterRow(
                label=f"{quantity} {slot or 'Total'}".strip(),
                quantity=quantity,  # type: ignore[arg-type]
                tod_slot=slot,
                present=_decimal(val(m.get("present"))),
                past=_decimal(val(m.get("past"))),
                difference=_decimal(val(m.get("difference"))),
                multiplying_factor=_decimal(val(m.get("multiplying_factor"))),
                gross_units=_decimal(val(m.get("consumption"))),
                open_access_units=_decimal(val(m.get("open_access"))),
                net_units=_decimal(val(m.get("net"))),
                page=m.get("page") if isinstance(m.get("page"), int) else None,
            )
        )
    tree["meters"] = tuple(meter_rows)

    items = []
    for i, ln in enumerate(lines):
        amount = _decimal(val(ln.get("amount")))
        if amount is None:
            continue
        items.append(
            LineItem(
                index=i,
                group=val(ln.get("group")),
                label=val(ln.get("label")) or "",
                kind=("info" if val(ln.get("detail_of")) else (val(ln.get("kind")) or "item")),  # type: ignore[arg-type]
                stage=val(ln.get("stage")) or "current",  # type: ignore[arg-type]
                quantity=_decimal(val(ln.get("quantity"))),
                rate=_decimal(val(ln.get("rate"))),
                rate_unit=val(ln.get("rate_unit")),
                unit=val(ln.get("unit")),
                amount=amount,
                tod_slot=val(ln.get("tod_slot")),
                code=val(ln.get("code")),
                signed=bool(ln.get("signed", False)),
                detail_of=val(ln.get("detail_of")),
                page=ln.get("page") if isinstance(ln.get("page"), int) else None,
            )
        )
    tree["line_items"] = tuple(items)
    tree["extraction_notes"] = tuple(extraction_notes)
    return Bill.model_validate(tree)
