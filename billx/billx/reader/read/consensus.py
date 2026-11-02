"""Consensus (build prompt 5.1, 5.3 steps 4 and 5): every reader's readings for a field are
gathered into one Value whose verdict is decide()'s. Arrays (meter rows, printed lines) are
matched item by item on their key, then compared field by field.

Nothing here chooses a value: `make_value` hands the readings to the rule.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from billx.core.normalize import FieldType, normalise
from billx.core.schema import Reading, Region, Unit, Value, make_value

ReaderName = str


@dataclass
class FieldSpec:
    path: str
    field_type: FieldType
    unit: Unit | None = None
    required: bool = False


@dataclass
class RawRead:
    """What a reader saw for one field before normalisation."""

    raw: str
    page: int | None = None
    region: Region | None = None


@dataclass
class ReaderOutput:
    """One reader's whole output for a bill: scalar fields by contract path, meter rows and
    printed lines as dicts of raw strings (keys: label, register, tod_slot, present, past,
    difference, multiplying_factor, consumption; and label, group, quantity, rate, unit,
    amount, kind, stage)."""

    reader: ReaderName
    method: str
    family: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    fields: dict[str, RawRead] = field(default_factory=dict)
    meters: list[dict[str, str | None]] = field(default_factory=list)
    lines: list[dict[str, str | None]] = field(default_factory=list)

    def reading(self, raw: RawRead, field_type: FieldType) -> Reading:
        return Reading(
            reader=self.reader,  # type: ignore[arg-type]
            method=self.method,  # type: ignore[arg-type]
            family=self.family,
            model_id=self.model_id,
            prompt_version=self.prompt_version,
            raw=raw.raw,
            normalised=normalise(raw.raw, field_type),
            page=raw.page,
            region=raw.region,
        )


def consensus_fields(outputs: Iterable[ReaderOutput], specs: Iterable[FieldSpec]) -> list[Value]:
    """One Value per field spec, from every reader that produced a reading for it."""
    outputs = list(outputs)
    values = []
    for spec in specs:
        readings = tuple(
            out.reading(out.fields[spec.path], spec.field_type)
            for out in outputs
            if spec.path in out.fields
        )
        values.append(make_value(spec.path, spec.field_type, readings, unit=spec.unit))
    return values


def _norm_key(text: str | None) -> str:
    return normalise(text or "", "text") or ""


def match_items(
    outputs: Iterable[ReaderOutput], kind: str, key_fields: tuple[str, ...]
) -> list[tuple[str, dict[str, list[tuple[ReaderOutput, str | None]]]]]:
    """Match array items across readers on their key (the normalised key fields joined). The
    result is, per key, the raw strings each reader gave for each item field. An item one
    reader has and another lacks keeps only its own readings, so it ends `unverified`.

    A key that no earlier reader produced is matched to the nearest existing key when the
    two differ by at most one character per eight (an OCR "Moming Peak" is "Morning Peak");
    the key is text, never a value, so this never changes what a reader read."""
    outputs = list(outputs)
    by_key: dict[str, dict[str, list[tuple[ReaderOutput, str | None]]]] = {}
    spellings: dict[str, list[str]] = {}  # every reader's spelling of a merged key
    order: list[str] = []
    for out in outputs:
        items = out.meters if kind == "meters" else out.lines
        seen: dict[str, int] = {}
        for item in items:
            key = " | ".join(_norm_key(item.get(k)) for k in key_fields)
            n = seen.get(key, 0)
            seen[key] = n + 1
            full = f"{key} #{n}" if n else key
            if full not in by_key:
                near = _nearest_key(full, [k for k in order if k not in seen_keys(out, by_key)])
                if near is not None:
                    full = near
                else:
                    by_key[full] = {}
                    order.append(full)
            spellings.setdefault(full, []).append(f"{key} #{n}" if n else key)
            for name, raw in item.items():
                if name in key_fields:
                    continue
                by_key[full].setdefault(name, []).append((out, raw))
    # a merged key is reported in the spelling most readers gave ("MORNING PEAK" over OCR's
    # "MOMING PEAK"); a tie is broken by how often each spelling's last part (the slot, the
    # label) occurs across every row of every reader, so the kWh rows settle the kVAh row's
    # name; a tie after that keeps the first reader's spelling
    everywhere: dict[str, int] = {}
    for parts in spellings.values():
        for v in parts:
            tail = v.split(" | ")[-1].split(" #")[0]
            everywhere[tail] = everywhere.get(tail, 0) + 1
    return [(_majority(spellings[k], everywhere), by_key[k]) for k in order]


def _majority(values: list[str], everywhere: dict[str, int]) -> str:
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1

    def rank(v: str) -> tuple[int, int, int]:
        tail = v.split(" | ")[-1].split(" #")[0]
        return (counts[v], everywhere.get(tail, 0), -values.index(v))

    return max(values, key=rank)


def seen_keys(out: ReaderOutput, by_key: dict) -> set[str]:
    """The keys this reader already filled, so one reader never matches two items to one."""
    return {k for k, cells in by_key.items() if any(o is out for v in cells.values() for o, _ in v)}


def _nearest_key(key: str, candidates: list[str]) -> str | None:
    best, best_d = None, None
    for c in candidates:
        limit = max(1, max(len(key), len(c)) // 8)
        d = _edit_distance(key, c, limit)
        if d is not None and d <= limit and (best_d is None or d < best_d):
            best, best_d = c, d
    return best


def _edit_distance(a: str, b: str, limit: int) -> int | None:
    """Levenshtein distance, or None once it exceeds `limit`."""
    if abs(len(a) - len(b)) > limit:
        return None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return None
        prev = cur
    return prev[-1]


def item_value(
    path: str,
    field_type: FieldType,
    readings_by_reader: list[tuple[ReaderOutput, str | RawRead | None]],
    unit: Unit | None = None,
    page: int | None = None,
) -> Value:
    # a reader that knows where it read a cell (the docling reader) gives a RawRead with its
    # page and box; the others give the printed string
    readings = tuple(
        out.reading(raw if isinstance(raw, RawRead) else RawRead(raw, page), field_type)
        for out, raw in readings_by_reader
        if raw is not None and (raw.raw if isinstance(raw, RawRead) else raw).strip() != ""
    )
    return make_value(path, field_type, readings, unit=unit)
