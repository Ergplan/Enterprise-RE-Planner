"""billx.reader.read.words: boxes as Decimal fractions, lines by overlap, segments by gaps."""

from decimal import Decimal

from billx.core.schema import Region
from billx.reader.read.words import (
    WordBox,
    detach_colons,
    frac,
    group_lines,
    line_text,
    region_of,
    segments,
    sort_reading_order,
    split_phrase,
)

D = Decimal


def box(text, x0, y0, x1, y1, page=0):
    return WordBox(text, page, D(x0), D(y0), D(x1), D(y1))


def test_frac_is_decimal_with_four_places_clamped():
    assert frac(1, 3) == D("0.3333") and isinstance(frac(1, 3), Decimal)
    assert frac(5, 4) == D("1") and frac(-1, 4) == D("0") and frac(1, 0) == D("0")
    assert frac(1654, 1654) == D("1")


def test_wordbox_region_and_union():
    w = box("x", "0.1", "0.2", "0.3", "0.25")
    assert w.region() == Region(x=D("0.1"), y=D("0.2"), w=D("0.2"), h=D("0.05"))
    v = box("y", "0.5", "0.1", "0.6", "0.3")
    assert region_of([w, v]) == Region(x=D("0.1"), y=D("0.1"), w=D("0.5"), h=D("0.2"))
    assert region_of([]) == Region(x=D(0), y=D(0), w=D(0), h=D(0))


def test_split_phrase_apportions_width_by_characters():
    words = split_phrase("AC-No : 99", 0, D("0.10"), D("0.2"), D("0.30"), D("0.21"), D("0.9"))
    assert [w.text for w in words] == ["AC-No", ":", "99"]
    assert words[0].x0 == D("0.10") and words[-1].x1 == D("0.30")
    assert words[0].x1 < words[1].x0 < words[1].x1 < words[2].x0
    assert all(w.confidence == D("0.9") and w.y0 == D("0.2") for w in words)
    assert split_phrase("   ", 0, D(0), D(0), D(1), D(1)) == []


def test_detach_colons_splits_glued_colons_only():
    words = detach_colons(
        [
            box("AC-No:", 0, 0, "0.1", "0.01"),
            box(":9912", "0.2", 0, "0.3", "0.01"),
            box("10:30", "0.4", 0, "0.5", "0.01"),
            box(":", "0.6", 0, "0.61", "0.01"),
        ]
    )
    assert [w.text for w in words] == ["AC-No", ":", ":", "9912", "10:30", ":"]


def test_group_lines_by_vertical_overlap_and_reading_order():
    a = box("second", "0.5", "0.10", "0.6", "0.12")
    b = box("first", "0.1", "0.105", "0.2", "0.125")  # overlaps a by more than half
    c = box("below", "0.1", "0.13", "0.2", "0.15")  # no overlap with the first line
    d = box("page2", "0.1", "0.10", "0.2", "0.12", page=1)
    lines = group_lines([c, a, d, b])
    assert [line_text(line) for line in lines] == ["first second", "below", "page2"]
    assert [w.text for w in sort_reading_order([c, a, b])] == ["first", "second", "below"]


def test_segments_split_at_wide_gaps():
    line = [
        box("KNO", "0.08", 0, "0.11", "0.01"),
        box("A/c", "0.30", 0, "0.32", "0.01"),
        box("No", "0.325", 0, "0.34", "0.01"),
    ]
    assert [line_text(s) for s in segments(line)] == ["KNO", "A/c No"]
    assert segments([]) == []
