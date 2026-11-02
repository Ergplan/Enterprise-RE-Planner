"""Layer 3, layout conformance S01 to S06 (Developer Guide section 6), run when the profile
version has a `template`:

    template:
      required_fields: [consumer.account_number, period.bill_month, ...]   # schema paths
      line_items:
        - {label_pattern: "energy charge", code: energy_charge, kind: item,
           stage: current, required: true}
      meters:
        - {label_pattern: "kvah total", quantity: kVAh}
      drift_threshold: 3

Below the drift threshold S01 and S02 fail (a few differences usually mean something was
missed); at or above it they downgrade to warnings and S06 flags drift (the utility probably
changed its layout).
"""

from __future__ import annotations

import re
from typing import Any

from billx.core.schema import Bill, CheckResult
from billx.reader.validate.registry import (
    CheckContext,
    check,
    line_path,
    meter_path,
    paths_for,
    result,
    skip,
)

DEFAULT_DRIFT = 3


def _field(bill: Bill, path: str) -> Any:
    obj: Any = bill
    for part in path.split("."):
        if obj is None or not hasattr(obj, part):
            return None
        obj = getattr(obj, part)
    return obj


def _ci(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE)


def _line_key(x) -> str:
    return f"{x.group or ''} :: {x.label}"


class Conformance:
    """One pass over the template against the bill; the S checks read its findings."""

    def __init__(self, bill: Bill, template: dict):
        self.bill = bill
        self.template = template
        self.threshold = int(template.get("drift_threshold") or DEFAULT_DRIFT)
        self.missing_fields = [
            p for p in template.get("required_fields") or [] if _field(bill, p) in (None, "")
        ]
        self.matched: dict[int, dict] = {}  # line index -> template entry
        self.missing_required: list[str] = []
        for entry in template.get("line_items") or []:
            rx = _ci(entry["label_pattern"])
            hits = [
                i
                for i, x in enumerate(bill.line_items)
                if rx.search(_line_key(x)) or rx.search(x.label)
            ]
            for i in hits:
                self.matched.setdefault(i, entry)
            if entry.get("required") and not hits:
                self.missing_required.append(entry["label_pattern"])
        self.extra_lines = [i for i in range(len(bill.line_items)) if i not in self.matched]
        self.kind_mismatch = [
            i
            for i, e in self.matched.items()
            if (e.get("kind") and bill.line_items[i].kind != e["kind"])
            or (e.get("stage") and bill.line_items[i].stage != e["stage"])
        ]
        self.meter_missing: list[str] = []
        matched_rows: set[int] = set()
        for entry in template.get("meters") or []:
            rx = _ci(entry["label_pattern"])
            hits = [
                i
                for i, r in enumerate(bill.meters)
                if (rx.search(r.label) or (r.tod_slot and rx.search(r.tod_slot)))
                and (not entry.get("quantity") or r.quantity == entry["quantity"])
            ]
            if not hits:
                self.meter_missing.append(entry["label_pattern"])
            matched_rows.update(hits)
        self.meter_extra = (
            [i for i in range(len(bill.meters)) if i not in matched_rows]
            if template.get("meters")
            else []
        )
        self.differences = (
            len(self.missing_fields)
            + len(self.missing_required)
            + len(self.extra_lines)
            + len(self.kind_mismatch)
            + len(self.meter_missing)
            + len(self.meter_extra)
        )
        self.drift = self.differences >= self.threshold


def _conf(bill: Bill, ctx: CheckContext) -> Conformance | None:
    if ctx.version is None or not ctx.version.template:
        return None
    return Conformance(bill, ctx.version.template)


def _hard(c: Conformance) -> str:
    return "warn" if c.drift else "fail"


@check(
    "S01",
    "fields the layout always carries are present",
    detects="a required field of the layout missing",
    applies_to="both",
)
def s01(bill: Bill, ctx: CheckContext) -> CheckResult:
    c = _conf(bill, ctx)
    if c is None:
        return skip("S01", "no template")
    return result(
        "S01",
        "pass" if not c.missing_fields else _hard(c),
        paths=paths_for(bill, *(c.template.get("required_fields") or [])),
        note=("missing:" + ",".join(c.missing_fields)) if c.missing_fields else None,
    )


@check(
    "S02",
    "every required template line was found",
    detects="a required line of the layout not captured",
    applies_to="both",
)
def s02(bill: Bill, ctx: CheckContext) -> CheckResult:
    c = _conf(bill, ctx)
    if c is None:
        return skip("S02", "no template")
    return result(
        "S02",
        "pass" if not c.missing_required else _hard(c),
        paths=tuple(line_path(i) for i in c.matched),
        note=f"missing_required:{len(c.missing_required)}" if c.missing_required else None,
    )


@check(
    "S03",
    "no line items outside the template",
    detects="a captured line the template does not know",
    severity="warn",
    applies_to="both",
)
def s03(bill: Bill, ctx: CheckContext) -> CheckResult:
    c = _conf(bill, ctx)
    if c is None:
        return skip("S03", "no template")
    return result(
        "S03",
        "pass" if not c.extra_lines else "warn",
        paths=tuple(line_path(i) for i in c.extra_lines),
        note=f"extra_lines:{len(c.extra_lines)}" if c.extra_lines else None,
    )


@check(
    "S04",
    "meter rows match the template",
    detects="a template meter row missing or a row outside the template",
    severity="warn",
    applies_to="both",
)
def s04(bill: Bill, ctx: CheckContext) -> CheckResult:
    c = _conf(bill, ctx)
    if c is None:
        return skip("S04", "no template")
    if not c.template.get("meters"):
        return skip("S04", "template has no meters")
    bad = c.meter_missing or c.meter_extra
    return result(
        "S04",
        "pass" if not bad else "warn",
        paths=tuple(meter_path(i, "label") for i in c.meter_extra),
        note=f"missing:{len(c.meter_missing)};extra:{len(c.meter_extra)}" if bad else None,
    )


@check(
    "S05",
    "matched lines use the template's kind and stage",
    detects="a matched line whose kind or stage differs from the template",
    severity="warn",
    applies_to="both",
)
def s05(bill: Bill, ctx: CheckContext) -> CheckResult:
    c = _conf(bill, ctx)
    if c is None:
        return skip("S05", "no template")
    return result(
        "S05",
        "pass" if not c.kind_mismatch else "warn",
        paths=tuple(line_path(i, "kind") for i in c.kind_mismatch),
        note=f"mismatched:{len(c.kind_mismatch)}" if c.kind_mismatch else None,
    )


@check(
    "S06",
    "layout drift: total differences below drift_threshold",
    detects="drift_threshold (default 3) or more differences from the template",
    severity="warn",
    applies_to="both",
)
def s06(bill: Bill, ctx: CheckContext) -> CheckResult:
    c = _conf(bill, ctx)
    if c is None:
        return skip("S06", "no template")
    return result(
        "S06",
        "warn" if c.drift else "pass",
        expected=f"<{c.threshold}",
        actual=str(c.differences),
        note="layout_drift" if c.drift else None,
    )


__all__ = ["DEFAULT_DRIFT", "Conformance"]
