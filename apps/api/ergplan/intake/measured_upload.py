"""Measured 15-minute load from a meter export (CSV): a timestamp column and a kW or kWh column.

The year starts at the first timestamp's 1 April (or the given start). Gaps are reported, not
filled silently: up to `max_gap_blocks` consecutive missing blocks are interpolated linearly and
counted; a longer gap rejects the file. kWh per block is converted to kW (× 4).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import LoadProfile
from .profile_synthesis import encode


class MeasuredFileError(ValueError):
    pass


@dataclass
class Measured:
    year_start: date
    kw: list[Decimal]
    unit: str
    rows: int
    interpolated: int
    duplicates: int
    gaps: list[str] = field(default_factory=list)


_TS_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
)


def _ts(s: str) -> datetime:
    s = s.strip()
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"timestamp {s!r}")


def parse(data: bytes, year_start: date | None = None, max_gap_blocks: int = 8) -> Measured:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))
    if len(rows) < 2:
        raise MeasuredFileError("the file has no data rows")
    header = [re.sub(r"[^a-z]", "", h.lower()) for h in rows[0]]
    c_ts = next(
        (i for i, h in enumerate(header) if h.startswith(("timestamp", "datetime", "time", "date"))), None
    )
    c_kw = next((i for i, h in enumerate(header) if h in ("kw", "demandkw", "loadkw", "activepowerkw")), None)
    c_kwh = next((i for i, h in enumerate(header) if h in ("kwh", "energykwh", "consumptionkwh")), None)
    if c_ts is None or (c_kw is None and c_kwh is None):
        raise MeasuredFileError("the header must name a timestamp column and a kW or kWh column")
    unit = "kW" if c_kw is not None else "kWh"
    col = c_kw if c_kw is not None else c_kwh
    assert col is not None
    seen: dict[datetime, Decimal] = {}
    duplicates = 0
    for n, r in enumerate(rows[1:], start=2):
        if not r or not "".join(r).strip():
            continue
        try:
            t = _ts(r[c_ts])
            v = Decimal(r[col].replace(",", "").strip())
        except (ValueError, IndexError, InvalidOperation) as e:
            raise MeasuredFileError(f"row {n}: {e}") from e
        if t.minute % 15 or t.second:
            raise MeasuredFileError(f"row {n}: {t:%Y-%m-%d %H:%M} is not on a quarter hour")
        if v < 0:
            raise MeasuredFileError(f"row {n}: negative load")
        if t in seen:
            duplicates += 1
        seen[t] = v * 4 if unit == "kWh" else v
    first = min(seen)
    start = year_start or date(first.year if first.month >= 4 else first.year - 1, 4, 1)
    t0 = datetime(start.year, start.month, start.day)
    t_end = datetime(start.year + 1, start.month, start.day)
    n_blocks = int((t_end - t0).total_seconds() // 900)
    series: list[Decimal | None] = [None] * n_blocks
    for t, v in seen.items():
        i = int((t - t0).total_seconds() // 900)
        if 0 <= i < n_blocks:
            series[i] = v
    gaps, interpolated, i = [], 0, 0
    while i < n_blocks:
        if series[i] is not None:
            i += 1
            continue
        j = i
        while j < n_blocks and series[j] is None:
            j += 1
        length = j - i
        when = f"{t0 + timedelta(minutes=15 * i):%Y-%m-%d %H:%M}, {length} blocks"
        if length > max_gap_blocks or i == 0 or j == n_blocks:
            gaps.append(when)
        else:
            a, b = series[i - 1], series[j]
            assert a is not None and b is not None
            for k in range(length):
                series[i + k] = (a + (b - a) * Decimal(k + 1) / Decimal(length + 1)).quantize(
                    Decimal("0.001")
                )
            interpolated += length
        i = j
    if gaps:
        shown = "; ".join(gaps[:5]) + (f"; and {len(gaps) - 5} more" if len(gaps) > 5 else "")
        raise MeasuredFileError(
            f"the year from {start} has gaps longer than {max_gap_blocks} blocks: {shown}"
        )
    kw = [v for v in series if v is not None]
    return Measured(start, kw, unit, len(seen), interpolated, duplicates, [])


def store(session: Session, connection_id: str, m: Measured, filename: str, sha256: str) -> LoadProfile:
    version = (
        session.scalar(
            select(func.max(LoadProfile.version)).where(LoadProfile.connection_id == connection_id)
        )
        or 0
    ) + 1
    method: dict[str, Any] = {
        "file": filename,
        "sha256": sha256,
        "unit_in_file": m.unit,
        "rows": m.rows,
        "interpolated_blocks": m.interpolated,
        "duplicate_timestamps": m.duplicates,
    }
    lp = LoadProfile(
        connection_id=connection_id,
        version=version,
        provenance="measured",
        resolution_min=15,
        year_start=m.year_start,
        blocks=len(m.kw),
        series_kw=encode(m.kw),
        method=method,
    )
    session.add(lp)
    session.flush()
    return lp
