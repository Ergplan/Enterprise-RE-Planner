"""The label rule (build prompt 5.3, step 1): for each scalar guaranteed field, the value
printed immediately right of, or directly below, one of the field's labels. Labels are the
regexes of `profiles/_common.yaml` `labels` (a profile version may add its own); the field
list is `config/guaranteed_fields.yaml`. No model value is involved.

How a value is found (each step is a heuristic, listed so it can be judged):

1. Words are grouped into lines and each line is split into segments at wide gaps (a cell or
   column boundary). A label must start at a segment start; the longest run of words from
   there that matches a label regex (case-insensitive, after dropping a trailing colon or a
   trailing bracketed unit such as "(SCM)") is the label. The first label in reading order
   wins for its field.
2. Right: the words after the label on the same line, with a leading ":" dropped, are the
   candidate. A number, date or month field takes the first token of its type anywhere to
   the right (a stray label is never number- or date-like). A text or identifier field takes
   the run of words up to the next wide gap when that run follows a colon or starts within
   one gap of the label ("AC-No : 9912345678").
3. Below: otherwise, the next line within 2.5 label heights that has a word overlapping the
   label's x-span gives its segment under the label ("KNO" over "994927801935"), read as in
   step 2.
4. Far right: a text or identifier field with nothing below takes the next segment to the
   right even across a wide gap ("Customer ID | SYNCG25192002" in a two-column table).
   A candidate for a text or identifier field is rejected when it is itself a label of some
   field, and an identifier must contain a digit (so "A/c No" beside "KNO" is never the
   account number).
5. `utility.name` is the whole line matching one of its patterns, as printed.
6. A period label (`period.from`, `period.to`, `period.bill_month`) whose value reads
   "<date> to <date>" gives `period.from` and `period.to` when their own labels are absent.
7. `charges.*` fields are table rows (billx.reader.read.rows), never label values, and a
   meter-reading row (five trailing numbers) never yields a label value: "KWH TOTAL" is a
   row, not the label of `energy.kwh`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from billx.core.normalize import FieldType, normalise
from billx.core.settings import load_config
from billx.reader.read.consensus import RawRead
from billx.reader.read.rows import is_meter_row
from billx.reader.read.words import (
    SEGMENT_GAP,
    WordBox,
    group_lines,
    line_text,
    region_of,
    segments,
)

PROFILES = Path(__file__).resolve().parents[3] / "profiles"
BELOW_REACH = Decimal("2.5")  # label heights a value line may sit below its label
COLON = ":"
_SHORT_CODE = re.compile(r"\(([A-Z][A-Z0-9&.-]{1,9})\)")
_TRAILING_UNIT = re.compile(r"\s*\([^()]*\)$")
_RANGE_SEP = re.compile(r"^(to|-|–|—|/)$", re.I)
_DIGIT = re.compile(r"\d")
# text that is a label or a column heading rather than a value: it ends in a colon, carries a
# unit in brackets, or is one of the words such headings use (seen as false values on real
# HPSEBL, MSEDCL and PVVNL bills, 23 Oct 2026)
_LABEL_LIKE = re.compile(
    r":\s*$|\((kw|kva|kv|kwh|kvah|rs\.?|₹|%)\)|"
    r"^(address|name|type|oa type|category|tariff|prev\.?\s*arrears?|arrears?|"
    r"connected load|sanctioned load|contract demand|supply voltage|standard ?supply ?voltage)\b",
    re.IGNORECASE,
)


def _mostly_digits(text: str) -> bool:
    """An identifier is at least half digits: account, consumer, meter and customer numbers."""
    alnum = [c for c in text if c.isalnum()]
    return bool(alnum) and sum(c.isdigit() for c in alnum) * 2 >= len(alnum)


_NUMERIC_BOX = re.compile(r"^[\d\s()+\-/]+$")
_MARKER = re.compile(r"^\d{1,2}$")
# what may stand between a label and its value: a currency mark, leaders, or the formula
# that names how it is made ("Current Bill Amount (Rs.) A + B+ C - G 1,823,331.00")
_FILLER = re.compile(r"^(rs\.?|₹|inr|\(rs\.?\)|\(₹\)|=|-|–|\.+|:|\+|[a-z][+\-]?)$", re.IGNORECASE)
_WORD_TOKEN = re.compile(r"^[^\W\d_][\w./&-]*$")
_PAIR_INSIDE = re.compile(r"\S\s*:\s*\S")
# the values a field can carry; a reading outside them is a neighbouring figure. A power
# factor is printed as a ratio (0 to 1) or a percentage (40 to 100)
_RANGES = {"energy.power_factor": ((Decimal(0), Decimal(1)), (Decimal(40), Decimal(100)))}


def sane(path: str, field_type: FieldType, read: RawRead) -> RawRead | None:
    """A reader's value as a value of its field, or None when it cannot be one: an identifier
    that is a month or date, or that carries words around one number ("Legacy A/C No.
    900012002423" gives the number; two numbers give none); a text value holding a "label :
    value" pair or an unclosed bracket ("CONSUMER)"); a number outside its field's range (a
    power factor of 1234567.89, or 8 from a footnote number). Seen on real AVVNL, PSPCL,
    HPSEBL, TNPDCL and DVVNL bills, 1 Nov 2026."""
    text = read.raw.strip()
    if field_type == "identifier":
        if any(normalise(text, t) is not None for t in ("date", "month")):
            return None
        tokens = text.split()
        if len(tokens) > 1 and any(_WORD_TOKEN.match(t) for t in tokens):
            numbers = [t for t in tokens if _DIGIT.search(t) and _mostly_digits(t)]
            others = [t for t in tokens if t not in numbers]
            if len(numbers) != 1 or not all(_WORD_TOKEN.match(t) for t in others):
                return None
            return RawRead(numbers[0], read.page, read.region)
        return read
    if field_type == "text" and path != "utility.name":  # the utility's line is printed whole
        if _PAIR_INSIDE.search(text) or text.count("(") != text.count(")"):
            return None
        return read
    if field_type == "number" and path in _RANGES:
        value = normalise(text, "number")
        if value is not None and not any(
            lo <= abs(Decimal(value)) <= hi for lo, hi in _RANGES[path]
        ):
            return None
    return read


@dataclass(frozen=True)
class FieldSpec:
    path: str
    field_type: FieldType


@lru_cache(maxsize=4)
def guaranteed_scalar_fields(bill_kind: str) -> tuple[FieldSpec, ...]:
    """The scalar guaranteed fields of `electricity` or `gas` (arrays are read as rows)."""
    fields = load_config("guaranteed_fields.yaml")[bill_kind]
    return tuple(FieldSpec(f["path"], f["type"]) for f in fields if f["type"] != "array")


@lru_cache(maxsize=1)
def common_labels() -> dict[str, tuple[re.Pattern, ...]]:
    """The generic label regexes of profiles/_common.yaml, compiled case-insensitive."""
    data = yaml.safe_load((PROFILES / "_common.yaml").read_text(encoding="utf-8"))
    return {path: tuple(re.compile(p, re.I) for p in pats) for path, pats in data["labels"].items()}


def _all_patterns(labels: dict[str, tuple[re.Pattern, ...]]) -> tuple[re.Pattern, ...]:
    return tuple(p for path, pats in labels.items() if path != "utility.name" for p in pats)


def is_typed(text: str, field_type: FieldType) -> bool:
    """Whether a token reads as a number, date or month (text and identifiers always do)."""
    if field_type in ("number", "date", "month"):
        return normalise(text, field_type) is not None
    return True


def label_match(segment: list[WordBox], patterns: tuple[re.Pattern, ...]) -> int:
    """The number of words from the segment start that form a label matching one of the
    patterns (the longest such run), 0 when none does."""
    for k in range(len(segment), 0, -1):
        text = " ".join(w.text for w in segment[:k])
        candidates = {text, text.rstrip(COLON).rstrip()}
        candidates.add(_TRAILING_UNIT.sub("", text.rstrip(COLON).rstrip()))
        # a bilingual label prints the local script, a slash, then English ("खाता/Account
        # No.:"); OCR without the local model turns the first part into noise
        for c in list(candidates):
            if "/" in c:
                candidates.add(c.rsplit("/", 1)[1].strip())
        for cand in candidates:
            if cand and any(p.fullmatch(cand) for p in patterns):
                return k
    return 0


def _raw(words: list[WordBox]) -> RawRead:
    return RawRead(" ".join(w.text for w in words), words[0].page, region_of(words))


_CONTINUATION = re.compile(r"^(&|and\b|of\b)", re.I)


LOAD_LABEL = re.compile(r"(?i)\bload\b(?!.*kva)")


def _load_in_kva(line: list[WordBox], label: list[WordBox]) -> RawRead | None:
    """A sanctioned load as the contract demand only when the figure is printed in kVA right
    after it ("Sanction Load : 600 kVA"); a load in kW or HP is not a demand in kVA."""
    rest = [w for w in line if w.x0 >= label[-1].x1 and w not in label]
    while rest and _FILLER.match(rest[0].text):
        rest = rest[1:]
    if len(rest) >= 2 and is_typed(rest[0].text, "number") and rest[1].text.lower() == "kva":
        return _raw(rest[:1])
    if rest and re.fullmatch(r"(?i)[\d,.]+kva", rest[0].text):
        return RawRead(rest[0].text[:-3], rest[0].page, region_of([rest[0]]))
    return None


def _in_prose(line: list[WordBox], label: list[WordBox]) -> bool:
    """Whether the label's words sit in a sentence ("Net Billed Units are the units used
    for ..."): a lower-case word follows them at once, so a figure below is not its value."""
    rest = [w for w in line if w.x0 >= label[-1].x1 and w not in label]
    return bool(rest) and rest[0].text[:1].islower()


def _table_row(line: list[WordBox], label: list[WordBox]) -> bool:
    """Whether the label heads a table row: four or more figures follow it ("Total kWh Energy |
    new | old | difference | multiplier | consumption"), so no single one is its value."""
    rest = [w for w in line if w.x0 >= label[-1].x1 and w not in label]
    return sum(1 for w in rest if normalise(w.text.rstrip("-"), "number") is not None) >= 4


class _Rule:
    """The label rule for one field type with the label set it must not mistake for values."""

    def __init__(self, field_type: FieldType, all_patterns: tuple[re.Pattern, ...]):
        self.field_type = field_type
        self.typed = field_type in ("number", "date", "month")
        self.all_patterns = all_patterns

    def _typed_value(self, run: list[WordBox]) -> RawRead | None:
        hit = next((w for w in run if is_typed(w.text, self.field_type)), None)
        return _raw([hit]) if hit else None

    def _text_value(self, run: list[WordBox]) -> RawRead | None:
        """The first segment of the run, unless it is itself a label or (for an identifier)
        carries no digit."""
        if not run:
            return None
        first = segments(run)[0]
        if label_match(first, self.all_patterns) == len(first):
            return None
        text = " ".join(w.text for w in first)
        if self.field_type == "identifier" and not _mostly_digits(text):
            return None
        if _LABEL_LIKE.search(text):
            return None  # a neighbouring label or heading, not a value
        if _CONTINUATION.match(text):
            return None  # the rest of a longer label ("& Address."), not a value
        if (
            self.field_type == "text"
            and len(first) > 1
            and _DIGIT.search(first[0].text)
            and normalise(first[0].text, "date") is not None
        ):
            return None  # a row of other values that starts with a date, not a name
        return _raw(first)

    def right(self, line: list[WordBox], label: list[WordBox]) -> tuple[RawRead | None, bool]:
        """(value immediately right, whether a far candidate was deferred). For a text or
        identifier field, "immediately" means after a colon or within one gap."""
        rest = [w for w in line if w.x0 >= label[-1].x1 and w not in label]
        if len(rest) >= 2 and _MARKER.match(rest[0].text) and rest[1].text == COLON:
            rest = rest[1:]  # a footnote number before the colon ("Power Factor 8 :")
        after_colon = bool(rest) and rest[0].text == COLON
        if after_colon:
            rest = rest[1:]
        if not rest:
            return None, False
        if self.typed:
            # the value is the first word after the label (a currency mark aside); a figure
            # further along belongs to whatever is printed between ("Payable by Due Date
            # Minimum Payable Amount 10" has no value right of its label)
            run = list(rest)
            while run and (_FILLER.match(run[0].text) or run[0].text.startswith("@")):
                # a rate annotation ("Due date rebate @1% 990.00", "@ 1%") is passed over
                run = run[2:] if run[0].text == "@" else run[1:]
            if (
                self.field_type == "month"
                and len(run) >= 2
                and not is_typed(run[0].text, "month")
                and is_typed(f"{run[0].text} {run[1].text}", "month")
            ):
                return _raw(run[:2]), False  # "May 2025"
            if not run or not is_typed(run[0].text, self.field_type):
                return None, False
            return self._typed_value(run[:1]), False
        close = after_colon or rest[0].x0 - label[-1].x1 <= SEGMENT_GAP
        if close:
            return self._text_value(rest), False
        return None, True

    def far_right(self, line: list[WordBox], label: list[WordBox]) -> RawRead | None:
        rest = [w for w in line if w.x0 >= label[-1].x1 and w not in label]
        return self._text_value(rest)

    def below(self, lines: list[list[WordBox]], i: int, label: list[WordBox]) -> RawRead | None:
        """The segment of the next line (within BELOW_REACH label heights) under the label's
        x-span; a typed field prefers the words inside the span."""
        x0, x1 = label[0].x0, label[-1].x1
        y1 = max(w.y1 for w in label)
        height = max(w.height for w in label)
        for line in lines[i + 1 :]:
            if line[0].page != label[0].page or line[0].y0 - y1 > BELOW_REACH * height:
                break
            if line[0].y0 < y1 - height / 2:
                continue  # the same printed line split in two, not a line below
            for segment in segments(line):
                if segment[-1].x1 > x0 and segment[0].x0 < x1:
                    if self.typed:
                        inside = [w for w in segment if w.x1 > x0 and w.x0 < x1]
                        return self._typed_value(inside or segment)
                    return self._text_value(segment)
        return None

    def value(self, lines: list[list[WordBox]], i: int, label: list[WordBox]) -> RawRead | None:
        if self.typed and (_table_row(lines[i], label) or _in_prose(lines[i], label)):
            return None
        value, deferred = self.right(lines[i], label)
        if value is None:
            value = self.below(lines, i, label)
        if value is None and deferred:
            value = self.far_right(lines[i], label)
        return value


def _utility_name(lines: list[list[WordBox]], patterns) -> RawRead | None:
    """The whole line that names the utility, as printed ("AJMER VIDYUT VITRAN NIGAM LIMITED
    (AVVNL)"): what a model transcribes too, so the readers can agree. The short code in
    brackets is not extracted; the discom id comes from the profile's match patterns."""
    for line in lines:
        text = line_text(line)
        if not any(p.search(text) for p in patterns):
            continue
        # the printed spans from the one that holds the name onwards, leaving out a purely
        # numeric box on the same line (a helpline number such as "1912"); a bracketed short
        # code after a wide gap ("(PVVNL)") stays
        segs = segments(line)
        start = next(
            (i for i, g in enumerate(segs) if any(p.search(line_text(g)) for p in patterns)), 0
        )
        kept = [w for g in segs[start:] if not _NUMERIC_BOX.match(line_text(g)) for w in g]
        return _raw(kept or line)
    return None


def _date_range(rest: list[WordBox]) -> tuple[RawRead, RawRead] | None:
    """ "<date> to <date>" among the words right of a period label."""
    dates = [(j, w) for j, w in enumerate(rest) if normalise(w.text, "date")]
    for (j, a), (k, b) in zip(dates, dates[1:], strict=False):
        between = rest[j + 1 : k]
        if len(between) == 1 and _RANGE_SEP.match(between[0].text):
            return _raw([a]), _raw([b])
    return None


def _looks_like_value(text: str) -> bool:
    return bool(_DIGIT.search(text)) and any(
        normalise(text.rstrip("/"), t) is not None for t in ("number", "date", "month")
    )


def _after(line: list[WordBox], label: list[WordBox]) -> list[WordBox]:
    rest = [w for w in line if w.x0 >= label[-1].x1 and w not in label]
    return rest[1:] if rest and rest[0].text == COLON else rest


def _value_follows(line: list[WordBox], label: list[WordBox], field_type: FieldType) -> bool:
    """Whether the word right after the label (after an optional colon) is a value of the
    field's type; a label found inside a segment counts only then."""
    rest = _after(line, label)
    return bool(rest) and is_typed(rest[0].text.rstrip("/"), field_type)


def _reading_pair(line: list[WordBox], label: list[WordBox]) -> tuple[RawRead, RawRead] | None:
    """A gas layout that prints "Meter Index 640493.63 / 789769.03" gives both readings
    through one label: the first number is the previous reading, the second the current.
    OCR may glue the slash to a number ("640493.63/" or "640493.63/789769.03")."""
    rest = _after(line, label)[:4]
    parts: list[tuple[str, WordBox]] = []
    for w in rest:
        for piece in w.text.split("/"):
            if piece.strip():
                parts.append((piece.strip(), w))
        if "/" not in w.text and not normalise(w.text, "number") and parts:
            break  # a word that is neither a number nor a separator ends the pair
    numbers = [(t, w) for t, w in parts if normalise(t, "number")]
    if len(numbers) < 2 or "/" not in " ".join(w.text for w in rest):
        return None
    (ta, wa), (tb, wb) = numbers[0], numbers[1]
    return (
        RawRead(ta, wa.page, region_of([wa])),
        RawRead(tb, wb.page, region_of([wb])),
    )


def read_labels(
    words: list[WordBox],
    bill_kind: str,
    labels: dict[str, tuple[re.Pattern, ...]] | None = None,
) -> dict[str, RawRead]:
    """`{path: RawRead}` for every scalar guaranteed field of `bill_kind` whose label and
    value were found. `labels` defaults to the common profile's."""
    labels = labels or common_labels()
    fields = [
        f
        for f in guaranteed_scalar_fields(bill_kind)
        if f.path in labels and f.path != "utility.name" and not f.path.startswith("charges.")
    ]
    lines = group_lines(words)
    rules = {f.path: _Rule(f.field_type, _all_patterns(labels)) for f in fields}
    found: dict[str, RawRead] = {}
    ranges: list[tuple[RawRead, RawRead]] = []
    period_patterns = tuple(
        p
        for path in ("period.from", "period.to", "period.bill_month")
        for p in labels.get(path, ())
    )
    for i, line in enumerate(lines):
        if is_meter_row(line):
            continue
        for segment in segments(line):
            for f in fields:
                if f.path in found:
                    continue
                # a text or identifier label must start its segment; a number, date or month
                # label may sit anywhere in one (OCR joins a whole row into one segment, and
                # a typed value is never mistaken for a label)
                starts = range(len(segment)) if rules[f.path].typed else range(1)
                for start in starts:
                    if start and _looks_like_value(segment[start].text):
                        continue  # a label never starts with a number or a date
                    k = label_match(segment[start:], labels[f.path])
                    if not k:
                        continue
                    label = segment[start : start + k]
                    if start and not _value_follows(line, label, f.field_type):
                        continue  # mid-segment: only when the typed value comes right after
                    if f.path in ("readings.previous", "readings.current"):
                        pair = _reading_pair(line, label)
                        if pair:
                            found.setdefault("readings.previous", pair[0])
                            found.setdefault("readings.current", pair[1])
                            break
                    if f.path == "demand.contract_kva" and LOAD_LABEL.search(
                        " ".join(w.text for w in label)
                    ):
                        value = _load_in_kva(lines[i], label)  # a load is a demand in kVA only
                    else:
                        value = rules[f.path].value(lines, i, label)
                    if value is not None:
                        found[f.path] = value
                        break
            # a "<date> to <date>" range may follow a period label anywhere in the segment
            # (OCR often joins a whole row into one segment); a date range is unambiguous
            for start in range(len(segment)):
                k = label_match(segment[start:], period_patterns)
                if not k:
                    continue
                label = segment[start : start + k]
                rest = [w for w in line if w.x0 >= label[-1].x1 and w not in label]
                pair = _date_range(rest[1:] if rest and rest[0].text == COLON else rest)
                if pair:
                    ranges.append(pair)
                    break
    if "utility.name" in labels and any(
        f.path == "utility.name" for f in guaranteed_scalar_fields(bill_kind)
    ):
        name = _utility_name(lines, labels["utility.name"])
        if name:
            found["utility.name"] = name
    kind_paths = {f.path for f in guaranteed_scalar_fields(bill_kind)}
    for start, end in ranges:
        if "period.from" in kind_paths and "period.from" not in found:
            found["period.from"] = start
        if "period.to" in kind_paths and "period.to" not in found:
            found["period.to"] = end
    types = {f.path: f.field_type for f in guaranteed_scalar_fields(bill_kind)}
    kept = {path: sane(path, types.get(path, "text"), read) for path, read in found.items()}
    return {path: read for path, read in kept.items() if read is not None}
