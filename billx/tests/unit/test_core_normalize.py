"""Normalisation (5.1): grouping, currency marks and numerals go; digits and sign stay."""

import pytest

from billx.core.normalize import normalise


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2,69,49,346.810", "26949346.81"),
        ("26,949,346.81", "26949346.81"),
        ("Rs. 1,500.00", "1500"),
        ("₹ 1500", "1500"),
        ("-0.73", "-0.73"),
        ("123.40 CR", "-123.4"),
        ("२,४३,५८,१५६.६०", "24358156.6"),
        ("6250", "6250"),
        ("0.00", "0"),
        ("12,400", "12400"),
        ("abc", None),
        ("1.2.3", None),
    ],
)
def test_numbers(raw, expected):
    assert normalise(raw, "number") == expected


def test_a_number_is_never_recomputed():
    # a leading-digit change is kept, not corrected
    assert normalise("3,43,58,156.60", "number") == "34358156.6"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("01-04-2025", "2025-04-01"),
        ("1/4/25", "2025-04-01"),
        ("01-APR-2025", "2025-04-01"),
        ("30 April 2025", "2025-04-30"),
        ("2025-04-30", "2025-04-30"),
        ("31-04-2025", None),
        ("12-MAR-2025 16:33", "2025-03-12"),
        ("01-APR-2025 00:00:00", "2025-04-01"),
        ("8/4/2025 10:15:13 AM", "2025-04-08"),
        ("soon", None),
    ],
)
def test_dates(raw, expected):
    assert normalise(raw, "date") == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("APR-2025", "2025-04"),
        ("Apr 2025", "2025-04"),
        ("04/2025", "2025-04"),
        ("2025-04", "2025-04"),
        ("April, 2025", "2025-04"),
        ("01-04-2025", "2025-04"),
        ("13/2025", None),
        ("202504", "2025-04"),
        ("202513", None),
        ("123456", None),
    ],
)
def test_months(raw, expected):
    assert normalise(raw, "month") == expected


def test_identifiers_keep_leading_zeros_and_lose_separators():
    assert normalise("00 12-34/56", "identifier") == "00123456"
    assert normalise("syn/1234/567", "identifier") == "SYN1234567"
    assert normalise("  ", "identifier") is None


def test_text_collapses_spaces_and_cases():
    assert normalise("  Dummy   Steel\nRolling Mills ", "text") == "DUMMY STEEL ROLLING MILLS"


def test_text_ignores_spaces_next_to_punctuation():
    assert normalise("NIGAM LTD. (PVVNL)", "text") == normalise("NIGAM LTD.(PVVNL)", "text")
    assert normalise("HV2 / PV", "text") == "HV2/PV"
