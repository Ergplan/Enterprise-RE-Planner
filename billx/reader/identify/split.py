"""Page sorting (build prompt 5.0): the pages of one file grouped into bills.

Several bills in one file (a month's bill and the one before it, scanned together) must become
several entries in `bills[]`, each read on its own pages only; read as one, a model mixes the two
months' tables and the checks fail on numbers that belong to different bills.

Signals, from each page's local text only (no model, no value leaves the page):

- `Page k of n`: k > 1 continues the bill before it; k = 1 starts a bill when one is open;
- the printed bill number: a page printing another bill number than the open bill starts a bill;
- the printed bill date: likewise, when both pages print one.

A page with none of these continues the open bill, so a file without signals stays one bill, as
before. Two readings of one bill number that differ in one character are the same number (OCR
noise across a bill's pages must never split it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from billx.core.normalize import normalise_date

_PAGE_OF = re.compile(r"(?i)\bpage\s*(\d{1,2})\s*of\s*(\d{1,2})\b")
_BILL_NO = re.compile(r"(?i)\bbill\s*(?:no|number)\b\.?\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]{5,24})")
_BILL_DATE = re.compile(
    r"(?i)\bbill\s*da[tf]e\b\s*[:\-]?\s*"
    r"(\d{1,2}[-/. ](?:[A-Za-z]{3,9}|\d{1,2})[-/. ]\d{2,4})"
)


@dataclass(frozen=True)
class PageSignals:
    page: int
    page_of: tuple[int, int] | None = None
    bill_no: str | None = None
    bill_date: str | None = None  # ISO


@dataclass
class _Group:
    pages: list[int] = field(default_factory=list)
    bill_no: str | None = None
    bill_date: str | None = None


def signals(page: int, text: str) -> PageSignals:
    m = _PAGE_OF.search(text)
    page_of = (int(m.group(1)), int(m.group(2))) if m else None
    if page_of and not (1 <= page_of[0] <= page_of[1]):
        page_of = None
    n = _BILL_NO.search(text)
    bill_no = re.sub(r"[^A-Z0-9]", "", n.group(1).upper()) if n else None
    d = _BILL_DATE.search(text)
    bill_date = normalise_date(d.group(1)) if d else None
    return PageSignals(page, page_of, bill_no or None, bill_date)


def _same_number(a: str, b: str) -> bool:
    """Equal, or one substitution, insertion or deletion apart."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) <= 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


def group_pages(texts: list[str]) -> list[tuple[int, ...]]:
    """Page numbers (1-based) per bill, in file order."""
    groups: list[_Group] = []
    for i, text in enumerate(texts):
        s = signals(i + 1, text)
        current = groups[-1] if groups else None
        new = current is None
        if current is not None and not (s.page_of and s.page_of[0] > 1):
            if s.page_of and s.page_of[0] == 1 and current.pages:
                new = True
            elif s.bill_no and current.bill_no and not _same_number(s.bill_no, current.bill_no):
                new = True
            elif s.bill_date and current.bill_date and s.bill_date != current.bill_date:
                new = True
        if new:
            groups.append(_Group())
            current = groups[-1]
        assert current is not None
        current.pages.append(i + 1)
        current.bill_no = current.bill_no or s.bill_no
        current.bill_date = current.bill_date or s.bill_date
    return [tuple(g.pages) for g in groups] or [tuple(range(1, len(texts) + 1))]
