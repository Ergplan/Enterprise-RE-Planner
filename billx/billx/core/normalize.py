"""Normalisation before two readings are compared (build prompt 5.1).

Every reader turns what it saw into a normalised string through these functions, and
`decide` compares the strings. Nothing here calculates a value: a number keeps its digits,
sign and decimal position; only grouping, currency marks, Devanagari numerals and trailing
zeros after the point are removed. A string that cannot be normalised for its type returns
None, and the reading counts as unparseable (never as a match).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

FieldType = Literal["number", "date", "month", "identifier", "text"]

_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")
_CURRENCY = re.compile(r"(?i)(rs\.?|inr|₹|rupees?)\s*")
_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")
_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for m in names
}


def normalise_number(raw: str) -> str | None:
    """'2,69,49,346.810' -> '26949346.81'; 'Rs. 1,500.00' -> '1500'; '(123.40)' -> '-123.40'
    is NOT applied (brackets are a layout convention G20 handles); 'CR' suffix -> negative."""
    s = raw.translate(_DEVANAGARI).strip()
    s = _CURRENCY.sub("", s)
    negative = False
    if s.lower().endswith(("cr", "cr.")):
        negative, s = True, re.sub(r"(?i)\s*cr\.?$", "", s)
    if s.lower().endswith("dr") or s.lower().endswith("dr."):
        s = re.sub(r"(?i)\s*dr\.?$", "", s)
    s = s.replace(",", "").replace(" ", "").replace("'", "")
    s = s.replace("−", "-").replace("–", "-")
    if s.startswith("-") and negative:
        s = s[1:]
    if not _NUMBER.match(s):
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    if negative:
        d = -d
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text


_TRAILING_TIME = re.compile(r"\s+\d{1,2}:\d{2}(:\d{2})?(\s*[ap]\.?m\.?)?$", re.I)


def _parse_date(raw: str) -> date | None:
    """A date as printed; a time printed after it ("12-MAR-2025 16:33") is not part of the
    date and is dropped (the reading-date columns of meter tables print both)."""
    s = _TRAILING_TIME.sub("", raw.translate(_DEVANAGARI).strip()).lower()
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s)
    # 01-04-2025, 01/04/25, 1.4.2025
    m = re.match(r"^(\d{1,2})[-/ ](\d{1,2})[-/ ](\d{2,4})$", s)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        y = y + 2000 if y < 100 else y
        return _safe_date(y, mo, d)
    # 2025-04-01 (ISO)
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return _safe_date(y, mo, d)
    # 01-APR-2025, 1 Apr 2025, 01 april 25
    m = re.match(r"^(\d{1,2})[-/ ]([a-z]{3,9})[-/ ](\d{2,4})$", s)
    if m and m.group(2) in _MONTHS:
        d, y = int(m.group(1)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        return _safe_date(y, _MONTHS[m.group(2)], d)
    # APR 01, 2025
    m = re.match(r"^([a-z]{3,9}) (\d{1,2}) (\d{4})$", s)
    if m and m.group(1) in _MONTHS:
        return _safe_date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))
    return None


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def normalise_date(raw: str) -> str | None:
    d = _parse_date(raw)
    return d.isoformat() if d else None


def normalise_month(raw: str) -> str | None:
    """'APR-2025', 'Apr 2025', '04/2025', '2025-04', 'April, 2025', '202504' -> '2025-04'.
    A full date is accepted and reduced to its month."""
    s = raw.translate(_DEVANAGARI).strip().lower()
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^([a-z]{3,9})[-/ ](\d{2,4})$", s)
    if m and m.group(1) in _MONTHS:
        y = int(m.group(2))
        y = y + 2000 if y < 100 else y
        return f"{y:04d}-{_MONTHS[m.group(1)]:02d}"
    m = re.match(r"^(\d{1,2})[-/ ](\d{4})$", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"
    m = re.match(r"^(\d{4})[-/ ](\d{1,2})$", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.match(r"^(20\d{2})(0[1-9]|1[0-2])$", s)
    if m:  # "202505", the billing month as AVVNL prints it
        return f"{m.group(1)}-{m.group(2)}"
    d = _parse_date(raw)
    return d.isoformat()[:7] if d else None


def normalise_identifier(raw: str) -> str | None:
    s = raw.translate(_DEVANAGARI)
    s = re.sub(r"[\s\-/]", "", s).upper()
    return s or None


_PUNCT_SPACE = re.compile(r"\s*([().,/:\-])\s*")


def normalise_text(raw: str) -> str | None:
    """Spaces collapsed, upper case, and no space next to punctuation: OCR and a text layer
    disagree on "LTD. (PVVNL)" against "LTD.(PVVNL)"; the words are the same."""
    s = re.sub(r"\s+", " ", raw.strip()).upper()
    s = _PUNCT_SPACE.sub(r"\1", s)
    return s or None


_BY_TYPE = {
    "number": normalise_number,
    "date": normalise_date,
    "month": normalise_month,
    "identifier": normalise_identifier,
    "text": normalise_text,
}


def normalise(raw: str, field_type: FieldType) -> str | None:
    """The normalised form of `raw` for its type, or None when it cannot be read as one."""
    return _BY_TYPE[field_type](raw)
