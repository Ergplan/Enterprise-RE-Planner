"""Shared helpers for the check tests: synthetic truths without rendering, the profile
context a bill gets, and the planted-misread mechanics (one value changed at one path)."""

from __future__ import annotations

import json
import random
from decimal import Decimal
from typing import Any

from billx.core.schema import Bill, CheckResult, LineItem
from billx.platform.synth import values
from billx.platform.synth.cli import _json
from billx.platform.synth.to_bill import bill_from_truth
from billx.reader.identify.profiles import match_discom, select_version
from billx.reader.validate.formula import run_checks
from billx.reader.validate.registry import CheckContext

SEEDS = (1, 2, 3)
ELECTRICITY_LAYOUTS = {"avvnl-ht-synth-v1": values.avvnl, "pvvnl-hv2-synth-v1": values.pvvnl}


def _truth(doc: dict) -> dict:
    """The truth-file form of a generator's output (strings, no `values`), as billx synth
    writes it."""
    return json.loads(_json({k: v for k, v in doc.items() if k != "values"}))


def electricity_truths() -> list[dict]:
    out = []
    for layout, gen in ELECTRICITY_LAYOUTS.items():
        for seed in SEEDS:
            for n in (1, 2):  # n odd: arrears; n even: none
                out.append(_truth(gen(random.Random(f"{seed}:{layout}_{n:02d}"), n)))
    return out


def gas_truths() -> list[dict]:
    out = []
    for style in ("a", "b"):
        for seed in SEEDS:
            out.append(_truth(values.gas(random.Random(f"{seed}:gas-{style}"), style)))
    return out


def clean_bills() -> list[Bill]:
    return [bill_from_truth(t) for t in electricity_truths() + gas_truths()]


def enriched_bills() -> list[Bill]:
    """Clean bills plus variants carrying what the synthetic layouts do not print: a group
    with a subtotal (G06), open access units (G04), net metering (G17)."""
    out = []
    for bill in clean_bills():
        if bill.bill_type != "electricity":
            continue
        items = tuple(
            x.model_copy(update={"group": "A"}) for x in bill.line_items if x.stage == "current"
        )
        sub = LineItem(
            index=len(items),
            group="A",
            label="Total (A)",
            kind="subtotal",
            amount=sum(x.amount for x in items),
        )
        out.append(bill.model_copy(update={"line_items": items + (sub,)}))
        t = total_rows(bill)[0]
        row = bill.meters[t]
        out.append(
            with_meter(bill, t, open_access_units=Decimal(1000), net_units=row.gross_units - 1000)
        )
        imp, exp = bill.energy.gross_kwh, Decimal(5000)
        out.append(
            with_section(
                bill,
                "energy",
                net_metering_import_kwh=imp,
                net_metering_export_kwh=exp,
                billed_units=imp - exp,
            )
        )
    return out


def context_for(bill: Bill) -> CheckContext:
    """The profile version the bill's printed name selects, as the integrator would."""
    discom = match_discom(bill.discom.name_as_printed or "")
    version = select_version(discom, bill.period.bill_month) if discom else None
    return CheckContext.for_version(version, bill.period.bill_month)


def results(bill: Bill, ctx: CheckContext | None = None) -> dict[str, CheckResult]:
    ctx = ctx or context_for(bill)
    out = {r.id: r for r in run_checks(bill, ctx)}
    assert len(out) == len(run_checks(bill, ctx)), "duplicate check ids"
    return out


# planting ---------------------------------------------------------------------------------


def _replace_in_tuple(items: tuple, index: int, **changes) -> tuple:
    return tuple(x.model_copy(update=changes) if i == index else x for i, x in enumerate(items))


def with_meter(bill: Bill, index: int, **changes) -> Bill:
    return bill.model_copy(update={"meters": _replace_in_tuple(bill.meters, index, **changes)})


def with_line(bill: Bill, index: int, **changes) -> Bill:
    return bill.model_copy(
        update={"line_items": _replace_in_tuple(bill.line_items, index, **changes)}
    )


def with_totals(bill: Bill, **changes) -> Bill:
    return bill.model_copy(update={"totals": bill.totals.model_copy(update=changes)})


def with_section(bill: Bill, section: str, **changes) -> Bill:
    return bill.model_copy(update={section: getattr(bill, section).model_copy(update=changes)})


def leading_digit_changed(d: Decimal) -> Decimal:
    """The number with its leading significant digit changed (1 -> 2, 9 -> 8, ...)."""
    text = format(abs(d), "f")
    for i, ch in enumerate(text):
        if ch.isdigit() and ch != "0":
            new = "2" if ch == "1" else str(int(ch) - 1)
            changed = Decimal(text[:i] + new + text[i + 1 :])
            return -changed if d < 0 else changed
    raise ValueError("no significant digit")


def meter_index(bill: Bill, quantity: str, slot: str | None) -> int:
    for i, r in enumerate(bill.meters):
        if r.quantity == quantity and r.tod_slot == slot:
            return i
    raise KeyError((quantity, slot))


def line_index(bill: Bill, code: str) -> int:
    for i, x in enumerate(bill.line_items):
        if x.code == code:
            return i
    raise KeyError(code)


def total_rows(bill: Bill) -> list[int]:
    return [i for i, r in enumerate(bill.meters) if not r.tod_slot]


def value_at(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj
