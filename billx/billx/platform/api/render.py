"""From the engine's result to the contract's wire shape (build prompt 6.1, 6.2, 6.5).

`esgos-1.0` is contract 1.0 exactly: the envelope and bill keys of contract sections 5.1 and
5.2, field objects with value/unit/printed/page/region/source, and nothing else. `esgos-1.1`
is the same shape with the optional additions of 6.5. A bill is rendered from the
`BillResult` the pipeline produced; nothing is decided here, only arranged, and in 1.0 mode
the printed-inconsistency flag becomes `passed: false` with a note, as 5.2 says.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from billx.core.schema import (
    ArrayValue,
    BillResult,
    CheckResult,
    Element,
    Envelope,
    TextEnvelope,
    Value,
)
from billx.reader.normalize.fields import guaranteed_fields

Mode = str  # "esgos-1.0" | "esgos-1.1"
CONTRACT_VERSION = {"esgos-1.0": "1.0", "esgos-1.1": "1.1"}


def _dec(x: Decimal | None) -> str | None:
    return None if x is None else format(x, "f")


def _region(v: Value) -> dict | None:
    if v.region is None:
        return None
    r = v.region
    return {"x": _dec(r.x), "y": _dec(r.y), "w": _dec(r.w), "h": _dec(r.h)}


def field_object(v: Value, mode: Mode) -> dict[str, Any]:
    """Contract 5.2's field object; 1.1 adds verification, proof and readers."""
    out: dict[str, Any] = {
        "value": v.value,
        "unit": v.unit,
        "printed": v.printed,
        "page": None if v.page is None else v.page + 1,
        "region": _region(v),
        "source": v.source,
    }
    if mode == "esgos-1.1":
        out["verification"] = v.verification
        out["proof"] = list(v.proof)
        out["readers"] = list(v.readers)
        # 1.1 adds every reader's own reading (optional): what each read and where, so a
        # person reviewing a disputed value sees the alternatives beside the page
        out["readings"] = [
            {
                "reader": r.reader,
                "printed": r.raw,
                "value": r.normalised,
                "page": None if r.page is None else r.page + 1,
                "region": None
                if r.region is None
                else {k: _dec(getattr(r.region, k)) for k in ("x", "y", "w", "h")},
            }
            for r in v.readings
            if r.reader != "human"
        ]
    return out


def _paths_for(bill_type: str, mode: Mode) -> list[dict]:
    fields = guaranteed_fields()[bill_type]
    if mode == "esgos-1.0":
        return [f for f in fields if f.get("contract") != "1.1"]
    return fields


def _set(tree: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    node = tree
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def _empty(path: str, unit: str | None, mode: Mode) -> dict:
    out: dict[str, Any] = {
        "value": None,
        "unit": unit,
        "printed": None,
        "page": None,
        "region": None,
        "source": None,
    }
    if mode == "esgos-1.1":
        out.update({"verification": "unverified", "proof": [], "readers": []})
    return out


def render_fields(bill: BillResult, mode: Mode) -> dict:
    """The guaranteed fields as a nested object: every contract path present, null where
    the bill doesn't print the value; arrays as lists of objects of field objects."""
    tree: dict = {}
    by_path = {v.path: v for v in bill.fields}
    arrays = dict(bill.arrays)
    for spec in _paths_for(bill.bill_type or "electricity", mode):
        path = spec["path"]
        if spec["type"] == "array":
            base = path[:-2]
            items = _render_array(path, arrays, spec, mode, bill)
            _set(tree, base, items)
            continue
        v = by_path.get(path)
        _set(tree, path, field_object(v, mode) if v else _empty(path, spec.get("unit"), mode))
    return tree


def _render_array(path: str, arrays: dict, spec: dict, mode: Mode, bill: BillResult) -> list:
    if path == "readings[]":
        return [_reading_item(item, mode) for item in arrays.get("readings[]", ())]
    if path == "energy.tod[]":
        readings = arrays.get("readings[]", ())
        out = [
            {"slot": item.key.split(" | ")[-1].title(), "kwh": field_object(item.fields[0], mode)}
            for item in _tod_items(readings)
        ]
        if mode == "esgos-1.1":
            # 1.1 adds the slot's kVAh, open-access and net units (optional fields): a bill
            # priced in kVAh prints its slots in kVAh only, and 1.0 had no place for them
            kvah = {_slot_of(i.key): i for i in _tod_items(readings, "KVAH")}
            for item in out:
                k = kvah.pop(_slot_of_title(item["slot"]), None)
                item.update(_tod_extra(k, mode))
            for slot_key, k in kvah.items():
                out.append({"slot": slot_key.title(), "kwh": None, **_tod_extra(k, mode)})
        return out
    if path == "charges.by_code[]":
        return [
            {"code": e.code, "amount": field_object(e.amount, mode)}
            for e in bill.elements
            if e.kind == "item" and e.stage == "current"
        ]
    return []


def _reading_item(item: ArrayValue, mode: Mode) -> dict:
    register, _, slot = item.key.partition(" | ")
    fields = {v.path.rsplit(".", 1)[-1]: v for v in item.fields}
    names = {"present": "current", "past": "previous", "multiplying_factor": "multiplying_factor"}
    out: dict[str, Any] = {
        "register": register.strip() or None,
        "tod_slot": None if slot.strip().upper() in ("", "TOTAL") else slot.strip().title(),
    }
    for src, dst in names.items():
        v = fields.get(src)
        out[dst] = field_object(v, mode) if v else None
    if mode == "esgos-1.1":
        # 1.1 adds each row's consumption, open-access and net units (optional fields)
        for src in ("consumption", "open_access", "net"):
            v = fields.get(src)
            out[src] = field_object(v, mode) if v else None
    return out


def _slot_of(key: str) -> str:
    return key.partition(" | ")[2].split(" #")[0].strip().upper()


def _slot_of_title(slot: str) -> str:
    return slot.split(" #")[0].strip().upper()


def _tod_extra(item: ArrayValue | None, mode: Mode) -> dict:
    """A slot's kVAh, open-access and net units (1.1)."""
    if item is None:
        return {"kvah": None, "open_access": None, "net": None}
    fields = {v.path.rsplit(".", 1)[-1]: v for v in item.fields}
    return {
        "kvah": field_object(fields["consumption"], mode) if "consumption" in fields else None,
        "open_access": field_object(fields["open_access"], mode)
        if "open_access" in fields
        else None,
        "net": field_object(fields["net"], mode) if "net" in fields else None,
    }


def _tod_items(readings: tuple[ArrayValue, ...], register_name: str = "KWH") -> list[ArrayValue]:
    """The slot rows of one register (its total row excluded). For kWh only the consumption
    cell is kept (contract 1.0's `energy.tod[]` item); for other registers every cell."""
    out = []
    for item in readings:
        register, _, slot = item.key.partition(" | ")
        if register.strip().upper() != register_name or slot.strip().upper() in ("", "TOTAL"):
            continue
        if register_name != "KWH":
            out.append(item)
            continue
        consumption = [v for v in item.fields if v.path.endswith(".consumption")]
        if consumption:
            out.append(ArrayValue(key=item.key, fields=(consumption[0],)))
    return out


def render_check(c: CheckResult) -> dict:
    return {
        "id": c.id,
        "description": c.description,
        "status": c.status,
        "expected": c.expected,
        "actual": c.actual,
        "tolerance": c.tolerance,
        "paths": list(c.paths),
    }


def render_element(e: Element, mode: Mode) -> dict:
    return {
        "index": e.index,
        "label": e.label,
        "group": e.group,
        "kind": e.kind,
        "stage": e.stage,
        "code": e.code,
        "quantity": e.quantity,
        "rate": e.rate,
        "unit": e.unit,
        "tod_slot": e.tod_slot,
        "amount": field_object(e.amount, mode),
        "formula_recheck": e.formula_recheck.model_dump(mode="json"),
        "tariff_recheck": e.tariff_recheck.model_dump(mode="json"),
    }


def render_bill(bill: BillResult, mode: Mode) -> dict:
    """Contract 5.2 for 1.0; the 6.5 additions on top for 1.1."""
    passed = bill.passed
    notes = list(bill.notes)
    if mode == "esgos-1.0" and bill.flags:
        # 1.0's own pass definition: a failing check fails the bill; the note says why
        passed = False
        notes = [n for n in notes if not n.startswith("printed_inconsistency:")]
        notes.extend(bill.flags)
    out: dict[str, Any] = {
        "index": bill.index,
        "pages": list(bill.pages),
        "bill_type": bill.bill_type,
        "utility": {
            "id": bill.utility.id,
            "name_as_printed": bill.utility.name_as_printed,
            "state": bill.utility.state,
        },
        "profile": {
            "id": bill.profile.id,
            "version": bill.profile.version,
            "status": bill.profile.status,
        },
        "route": bill.route,
        "fields": render_fields(bill, mode),
        "data": bill.data.model_dump(mode="json") if bill.data else None,
        "checks": [render_check(c) for c in bill.checks],
        "passed": passed,
        "unread_reason": bill.unread_reason,
        "notes": notes,
    }
    if mode == "esgos-1.1":
        out.update(
            {
                "status": bill.status,
                "review_reasons": list(bill.review_reasons),
                "flags": list(bill.flags),
                "accepted": bill.accepted,
                "accepted_by": bill.accepted_by,
                "proof_rule_version": bill.proof_rule_version,
                "routes_used": list(bill.routes_used),
                "document_type": bill.document_type,
                "audit_status": bill.audit_status,
                "elements": [render_element(e, mode) for e in bill.elements],
                "tariff_recheck": {
                    "status": "not_computable",
                    "reason": "tariff_engine_pending",
                    "elements": [e.tariff_recheck.model_dump(mode="json") for e in bill.elements],
                },
                "insights": [],
            }
        )
    return out


def render_envelope(env: Envelope, mode: Mode) -> dict:
    return {
        "contract_version": CONTRACT_VERSION[mode],
        "engine_version": env.engine_version,
        "schema_version": env.schema_version,
        "file": {
            "sha256": env.file.sha256,
            "pages": env.file.pages,
            "media_type": env.file.media_type,
        },
        "bills": [render_bill(b, mode) for b in env.bills],
        "usage": [
            {
                "provider": u.provider,
                "model": u.model,
                "purpose": u.purpose,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cost_usd": _dec(u.cost_usd),
            }
            for u in env.usage
        ],
        "seconds": _dec(env.seconds),
    }


def render_text(env: TextEnvelope, mode: Mode) -> dict:
    """Contract 5.3: pages with text and words; nothing extracted."""
    return {
        "contract_version": CONTRACT_VERSION[mode],
        "engine_version": env.engine_version,
        "schema_version": env.schema_version,
        "file": {
            "sha256": env.file.sha256,
            "pages": env.file.pages,
            "media_type": env.file.media_type,
        },
        "pages": [
            {
                "page": p.page,
                "text": p.text,
                "words": [
                    {
                        "text": w.text,
                        "region": {
                            "x": _dec(w.region.x),
                            "y": _dec(w.region.y),
                            "w": _dec(w.region.w),
                            "h": _dec(w.region.h),
                        },
                    }
                    for w in p.words
                ],
            }
            for p in env.pages
        ],
        "usage": [],
        "seconds": _dec(env.seconds),
    }


CONTRACT_1_0_BILL_KEYS = frozenset(
    {
        "index",
        "pages",
        "bill_type",
        "utility",
        "profile",
        "route",
        "fields",
        "data",
        "checks",
        "passed",
        "unread_reason",
        "notes",
    }
)
CONTRACT_1_0_FIELD_KEYS = frozenset({"value", "unit", "printed", "page", "region", "source"})
