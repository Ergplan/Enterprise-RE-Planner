"""Find the pages of an order that print a topic, by phrase patterns on the text layer. The
patterns are deliberately specific (tariff-oder's lesson: a bare `banking` matches "internet
banking" and "Banking and Finance Charges")."""

from __future__ import annotations

import re

from ..db.models import SourceDocument
from ..documents import service as documents

TOPICS: dict[str, str] = {
    "rate_schedule": r"rate\s+schedule|annexure[- ]?i\b|tariff\s+schedule",
    "tod": r"\btime\s+of\s+day\b|\bTOD\b|\bToD\b|\bTOU\b|time\s+of\s+use",
    "cross_subsidy_surcharge": r"cross[- ]subsidy\s+surcharge",
    "additional_surcharge": r"additional\s+surcharge",
    "wheeling": r"wheeling\s+(charges?|losses)",
    "transmission": r"transmission\s+charges?|intra[- ]state\s+transmission",
    "banking": r"banking\s+of\s+(power|energy)|banked\s+(units|energy|power)|banking\s+charges?",
    "green_tariff": r"green\s+(energy\s+)?tariff",
    "open_access": r"open\s+access",
}


def category_pattern(code: str) -> str:
    """'HV-2' → a pattern matching 'HV-2', 'HV – 2', 'HV 2'."""
    m = re.match(r"([A-Za-z]+)\W*(\w+)", code)
    if not m:
        return re.escape(code)
    return rf"\b{m.group(1)}\s*[-–]?\s*{m.group(2)}\b"


def locate(
    doc: SourceDocument, pattern: str, within: tuple[int, int] | None = None, top: int = 12
) -> list[tuple[int, int]]:
    """(page, hits) for the pages that match most, best first."""
    rx = re.compile(TOPICS.get(pattern, pattern), re.I)
    lo, hi = within or (1, doc.pages)
    scored = []
    for p in range(max(1, lo), min(doc.pages, hi) + 1):
        n = len(rx.findall(documents.page_text(doc, p)))
        if n:
            scored.append((p, n))
    return sorted(scored, key=lambda x: (-x[1], x[0]))[:top]
