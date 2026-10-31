"""IEX market prices from the analyst's upload (xlsx or csv) into `price_series`, one vintage per file.

Accepted layout (IEX's 15-minute market snapshot, as jouleWise keeps it): a header row naming
`Date`, `Time Block` ('00:00-00:15' or '00:00 - 00:15'), `MCP (₹/MWh)` and optionally `MCV (MW)`,
`Session ID` (RTM) and `Scraped At` (DAM). The segment comes from the caller, or from the file name
(DAM, RTM, GDAM, GTAM, HPDAM, TAM), or from a `Session ID` column (RTM).

Duplicates of one (day, block) are common in scraped files: identical rows are dropped; rows that
disagree keep the latest `Scraped At` (or the last in file order) and are counted as conflicts.
The vintage records the file's SHA-256, row counts, duplicates and conflicts, so every price a
client sees names the exact file it came from (invariant 8).
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

SEGMENTS = ("dam", "rtm", "gdam", "gtam", "hpdam", "tam")


class PriceFileError(ValueError):
    pass


@dataclass(frozen=True)
class PriceRow:
    day: date
    block: int  # 1..96, block 1 = 00:00-00:15
    mcp_inr_per_mwh: Decimal
    mcv_mw: Decimal | None


@dataclass
class ParsedPrices:
    segment: str
    sha256: str
    rows: list[PriceRow]
    rows_read: int
    duplicates_dropped: int
    conflicts: int
    skipped: list[str] = field(default_factory=list)

    @property
    def date_from(self) -> date:
        return min(r.day for r in self.rows)

    @property
    def date_to(self) -> date:
        return max(r.day for r in self.rows)

    def missing_blocks(self) -> int:
        days = (self.date_to - self.date_from).days + 1
        return days * 96 - len(self.rows)


def segment_from_name(filename: str) -> str | None:
    stem = re.sub(r"\b(g|hp)[-_ ](dam|tam)\b", r"\1\2", filename.lower())  # G-TAM, HP-DAM
    for seg in ("hpdam", "gdam", "gtam", "dam", "rtm", "tam"):  # longest first
        if re.search(rf"(^|[^a-z]){seg}([^a-z]|$)", stem):
            return seg
    return None


def _norm(h: Any) -> str:
    return re.sub(r"[^a-z]", "", str(h or "").lower())


def _column(header: list[Any], *prefixes: str) -> int | None:
    names = [_norm(h) for h in header]
    for p in prefixes:
        for i, n in enumerate(names):
            if n.startswith(p):
                return i
    return None


def _day(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date {s!r}")


def _block(v: Any) -> int:
    s = str(v).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$", s)
    if m:
        start = int(m.group(1)) * 60 + int(m.group(2))
        if start % 15 or start >= 1440:
            raise ValueError(f"time block {s!r}")
        return start // 15 + 1
    if s.isdigit() and 1 <= int(s) <= 96:
        return int(s)
    raise ValueError(f"time block {s!r}")


def _dec(v: Any) -> Decimal | None:
    if v is None or str(v).strip() in ("", "-", "NA"):
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except InvalidOperation as e:
        raise ValueError(f"number {v!r}") from e


def _scraped(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip().lower()
    for fmt in ("%d/%m/%Y, %I:%M:%S %p", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _table(data: bytes, filename: str) -> list[list[Any]]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # openpyxl raises several types for a bad file
            raise PriceFileError(f"not a readable workbook: {type(e).__name__}") from e
        ws = wb["15min"] if "15min" in wb.sheetnames else wb[wb.sheetnames[0]]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    text = data.decode("utf-8-sig", errors="replace")
    return [list(r) for r in csv.reader(io.StringIO(text))]


def parse(data: bytes, filename: str, segment: str | None = None) -> ParsedPrices:
    table = _table(data, filename)
    hi = next((i for i, r in enumerate(table[:20]) if _column(r, "mcp") is not None), None)
    if hi is None:
        raise PriceFileError("no header row with an MCP column in the first 20 rows")
    header = table[hi]
    c_date, c_block, c_mcp = (
        _column(header, "date", "deliverydate"),
        _column(header, "timeblock", "block"),
        _column(header, "mcp"),
    )
    c_mcv, c_session, c_scraped = (
        _column(header, "mcv"),
        _column(header, "sessionid"),
        _column(header, "scrapedat"),
    )
    if c_date is None or c_block is None or c_mcp is None:
        raise PriceFileError("the header must name Date, Time Block and MCP")
    seg = (segment or segment_from_name(filename) or ("rtm" if c_session is not None else None) or "").lower()
    if seg not in SEGMENTS:
        raise PriceFileError("say which market segment the file holds (dam, rtm, gdam, gtam, hpdam, tam)")
    best: dict[tuple[date, int], tuple[datetime | None, int, PriceRow]] = {}
    duplicates = conflicts = rows_read = 0
    skipped: list[str] = []
    for n, r in enumerate(table[hi + 1 :], start=hi + 2):
        if not r or all(v in (None, "") for v in r):
            continue
        rows_read += 1
        try:
            mcp = _dec(r[c_mcp])
            if mcp is None:
                raise ValueError("no MCP")
            row = PriceRow(
                _day(r[c_date]), _block(r[c_block]), mcp, _dec(r[c_mcv]) if c_mcv is not None else None
            )
        except (ValueError, IndexError) as e:
            if len(skipped) < 50:
                skipped.append(f"row {n}: {e}")
            continue
        key = (row.day, row.block)
        stamp = _scraped(r[c_scraped]) if c_scraped is not None else None
        prev = best.get(key)
        if prev is None:
            best[key] = (stamp, n, row)
            continue
        duplicates += 1
        if prev[2] != row:
            conflicts += 1
            newer = (stamp or datetime.min, n) >= (prev[0] or datetime.min, prev[1])
            if newer:
                best[key] = (stamp, n, row)
    if not best:
        raise PriceFileError("no price rows could be read")
    rows = [v[2] for _, v in sorted(best.items())]
    return ParsedPrices(
        seg, hashlib.sha256(data).hexdigest(), rows, rows_read, duplicates, conflicts, skipped
    )


# ---------------------------------------------------------------- storage


class OverlappingVintage(ValueError):
    def __init__(self, vintage_ids: list[str]):
        super().__init__("prices for these dates are already loaded; choose replace to supersede them")
        self.vintage_ids = vintage_ids


def store(
    session: Any,
    parsed: ParsedPrices,
    filename: str,
    actor: str,
    replace: bool = False,
    source_note: str | None = None,
) -> Any:
    """One vintage per file. A file whose dates overlap a live vintage of the same segment is
    refused unless `replace`, which marks the old vintages superseded (their rows stay, so runs
    that pinned them replay identically)."""
    from sqlalchemy import insert, select

    from ..db.models import PricePoint, PriceVintage

    same = session.scalars(
        select(PriceVintage).where(
            PriceVintage.file_sha256 == parsed.sha256,
            PriceVintage.segment == parsed.segment,
            PriceVintage.superseded_by.is_(None),
        )
    ).first()
    if same is not None:
        return same
    live = list(
        session.scalars(
            select(PriceVintage).where(
                PriceVintage.segment == parsed.segment,
                PriceVintage.superseded_by.is_(None),
                PriceVintage.date_from <= parsed.date_to,
                PriceVintage.date_to >= parsed.date_from,
            )
        )
    )
    if live and not replace:
        raise OverlappingVintage([v.id for v in live])
    v = PriceVintage(
        segment=parsed.segment,
        filename=filename,
        file_sha256=parsed.sha256,
        rows=len(parsed.rows),
        duplicates_dropped=parsed.duplicates_dropped,
        date_from=parsed.date_from,
        date_to=parsed.date_to,
        source_note=source_note
        or (
            f"{parsed.conflicts} conflicting duplicates resolved to the latest" if parsed.conflicts else None
        ),
        uploaded_by=actor,
    )
    session.add(v)
    session.flush()
    for old in live:
        old.superseded_by = v.id
    batch = [
        {
            "vintage_id": v.id,
            "day": r.day,
            "block": r.block,
            "segment": parsed.segment,
            "mcp_inr_per_mwh": r.mcp_inr_per_mwh,
            "mcv_mw": r.mcv_mw,
        }
        for r in parsed.rows
    ]
    for i in range(0, len(batch), 5000):
        session.execute(insert(PricePoint), batch[i : i + 5000])
    return v


def coverage(session: Any, segment: str | None = None) -> list[dict[str, Any]]:
    """Blocks loaded per day and segment from live vintages, for the analyst's coverage calendar."""
    from sqlalchemy import func, select

    from ..db.models import PricePoint, PriceVintage

    q = (
        select(PricePoint.segment, PricePoint.day, func.count(), func.min(PricePoint.vintage_id))
        .join(PriceVintage, PriceVintage.id == PricePoint.vintage_id)
        .where(PriceVintage.superseded_by.is_(None))
        .group_by(PricePoint.segment, PricePoint.day)
        .order_by(PricePoint.segment, PricePoint.day)
    )
    if segment:
        q = q.where(PricePoint.segment == segment)
    return [
        {"segment": s, "day": d.isoformat(), "blocks": n, "vintage_id": vid}
        for s, d, n, vid in session.execute(q)
    ]
