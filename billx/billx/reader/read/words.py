"""Words with boxes: the one shape every local reader produces and the label rule and the
row rules consume (build prompt 5.1).

A `WordBox` is one printed word with its box as fractions of the page (Decimal, 4 places,
from the top left). The helpers group words into lines by vertical overlap, sort them into
reading order, split a line into segments at wide horizontal gaps (a table cell boundary or
a column of a key-value layout), and build a `billx.core.schema.Region` from any run of
words. Nothing here reads a value: these are geometry helpers only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from billx.core.schema import Region

PLACES = Decimal("0.0001")
ONE = Decimal(1)
ZERO = Decimal(0)
# A horizontal gap wider than this fraction of the page width separates two segments of a
# line: on an A4 page it is about 12 pt, more than any space between words of one phrase and
# less than the gap between two cells or two columns of the layouts seen so far.
SEGMENT_GAP = Decimal("0.02")
# Two words are on one line when their vertical overlap is at least this share of the
# shorter word's height.
SKEW_PER_WIDTH = Decimal("0.015")  # vertical drift allowed per unit of horizontal distance


def frac(numerator: float | int | Decimal, denominator: float | int | Decimal) -> Decimal:
    """`numerator / denominator` as a Decimal fraction with four places, clamped to [0, 1]."""
    if not denominator:
        return ZERO
    value = Decimal(str(numerator)) / Decimal(str(denominator))
    return min(max(value, ZERO), ONE).quantize(PLACES, ROUND_HALF_UP)


@dataclass(frozen=True)
class WordBox:
    """One word and its box: fractions of the page width and height from the top left."""

    text: str
    page: int
    x0: Decimal
    y0: Decimal
    x1: Decimal
    y1: Decimal
    confidence: Decimal | None = None

    @property
    def height(self) -> Decimal:
        return self.y1 - self.y0

    @property
    def width(self) -> Decimal:
        return self.x1 - self.x0

    def region(self) -> Region:
        return Region(x=self.x0, y=self.y0, w=self.width, h=self.height)


def region_of(words: Iterable[WordBox]) -> Region:
    """The Region covering every word given (the union of their boxes)."""
    words = list(words)
    if not words:
        return Region(x=ZERO, y=ZERO, w=ZERO, h=ZERO)
    x0 = min(w.x0 for w in words)
    y0 = min(w.y0 for w in words)
    x1 = max(w.x1 for w in words)
    y1 = max(w.y1 for w in words)
    return Region(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def split_phrase(
    text: str, page: int, x0: Decimal, y0: Decimal, x1: Decimal, y1: Decimal, confidence=None
) -> list[WordBox]:
    """Words of a phrase read as one box (an OCR text line), each given a share of the box's
    width in proportion to its characters, spaces included. Approximate boxes, exact text."""
    parts = [(m.start(), m.group()) for m in re.finditer(r"\S+", text)]
    if not parts:
        return []
    total = max(len(text), 1)
    width = x1 - x0
    words = []
    for start, part in parts:
        wx0 = (x0 + width * Decimal(start) / Decimal(total)).quantize(PLACES, ROUND_HALF_UP)
        wx1 = (x0 + width * Decimal(start + len(part)) / Decimal(total)).quantize(
            PLACES, ROUND_HALF_UP
        )
        words.append(WordBox(part, page, wx0, y0, wx1, y1, confidence))
    return words


def detach_colons(words: Iterable[WordBox]) -> list[WordBox]:
    """A colon glued to the front or the back of a word becomes its own word ("AC-No:" ->
    "AC-No", ":"; ":9912" -> ":", "9912"), with the box split in proportion to the characters,
    so the label rule sees the same tokens from the text layer and from OCR."""
    out: list[WordBox] = []
    for w in words:
        text = w.text
        if len(text) > 1 and (text.startswith(":") or text.endswith(":")):
            out.extend(
                split_phrase(
                    text.replace(":", " : ", 1) if text.startswith(":") else text[:-1] + " :",
                    w.page,
                    w.x0,
                    w.y0,
                    w.x1,
                    w.y1,
                    w.confidence,
                )
            )
        else:
            out.append(w)
    return out


def group_lines(words: Iterable[WordBox]) -> list[list[WordBox]]:
    """Lines of words, top to bottom, each left to right.

    A word joins the line on which its nearest neighbour in x has a vertical centre within
    half the smaller of the two heights of its own centre, plus a skew allowance of
    SKEW_PER_WIDTH times the horizontal distance to that neighbour (a scanned page is rarely
    perfectly level: on the synthetic scans a row drifts about 0.009 of the page height across
    its width, while rows are 0.018 apart). Comparing with the nearest neighbour, not with the
    union of the line's extent, keeps a line from drifting down the page and swallowing the
    row beneath it (the OCR box of a small label and of the bold value under it differ in
    height). The closest qualifying line wins. Words of different pages never share a line.
    """
    lines: list[dict] = []
    for w in sorted(words, key=lambda w: (w.page, w.y0, w.x0)):
        centre = (w.y0 + w.y1) / 2
        best = None
        for line in lines:
            if line["page"] != w.page:
                continue
            nearest = min(line["words"], key=lambda o: _x_gap(o, w))
            tolerance = min(w.height, nearest.height) / 2 + SKEW_PER_WIDTH * _x_gap(nearest, w)
            distance = abs(centre - (nearest.y0 + nearest.y1) / 2)
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, line)
        if best is None:
            lines.append({"page": w.page, "words": [w]})
        else:
            best[1]["words"].append(w)
    lines.sort(key=lambda line: (line["page"], _median([(o.y0 + o.y1) / 2 for o in line["words"]])))
    return [sorted(line["words"], key=lambda w: (w.x0, w.x1)) for line in lines]


def _x_gap(a: WordBox, b: WordBox) -> Decimal:
    """Horizontal distance between two boxes (zero when they overlap in x)."""
    return max(ZERO, max(a.x0, b.x0) - min(a.x1, b.x1))


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def sort_reading_order(words: Iterable[WordBox]) -> list[WordBox]:
    """The words line by line, left to right within each line."""
    return [w for line in group_lines(words) for w in line]


def line_text(line: Iterable[WordBox]) -> str:
    """The words of a line joined by single spaces."""
    return " ".join(w.text for w in line)


def segments(line: list[WordBox], gap: Decimal = SEGMENT_GAP) -> list[list[WordBox]]:
    """The line split where the horizontal gap between two consecutive words exceeds `gap`."""
    out: list[list[WordBox]] = []
    for w in line:
        if out and w.x0 - out[-1][-1].x1 <= gap:
            out[-1].append(w)
        else:
            out.append([w])
    return out
