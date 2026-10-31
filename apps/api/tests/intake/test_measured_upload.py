from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from ergplan.intake import measured_upload


def _csv(unit: str = "kW", skip: set[int] | None = None, start: datetime = datetime(2026, 4, 1)) -> bytes:
    lines = [f"timestamp,{unit}"]
    for i in range(365 * 96):
        if skip and i in skip:
            continue
        lines.append(f"{start + timedelta(minutes=15 * i):%Y-%m-%d %H:%M},{100 + i % 96}")
    return ("\n".join(lines) + "\n").encode()


def test_full_year_in_kw() -> None:
    m = measured_upload.parse(_csv())
    assert m.year_start == date(2026, 4, 1) and len(m.kw) == 365 * 96
    assert m.kw[0] == Decimal("100") and m.interpolated == 0


def test_kwh_is_converted_and_short_gaps_interpolated() -> None:
    m = measured_upload.parse(_csv("kWh", skip={10, 11}))
    assert m.kw[0] == Decimal("400")  # 100 kWh in 15 minutes = 400 kW
    assert m.interpolated == 2
    assert m.kw[9] < m.kw[10] < m.kw[11] < m.kw[12]


def test_long_gap_rejects() -> None:
    with pytest.raises(measured_upload.MeasuredFileError, match="gaps"):
        measured_upload.parse(_csv(skip=set(range(100, 120))))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"timestamp,kW\n", "no data rows"),
        (b"when,load\n2026-04-01 00:00,1\n", "header"),
        (b"timestamp,kW\n2026-04-01 00:07,1\n", "quarter hour"),
        (b"timestamp,kW\n2026-04-01 00:00,-1\n", "negative"),
        (b"timestamp,kW\nyesterday,1\n", "row 2"),
    ],
)
def test_bad_files(data: bytes, message: str) -> None:
    with pytest.raises(measured_upload.MeasuredFileError, match=message):
        measured_upload.parse(data)
