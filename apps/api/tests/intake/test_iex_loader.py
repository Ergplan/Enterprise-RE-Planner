"""IEX loader: both snapshot layouts, segment detection, duplicates and conflicts, vintages with
overlap refusal and replace, coverage; the real files when present (data/iex, gitignored)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from ergplan.db.base import session_scope
from ergplan.db.models import PricePoint, PriceVintage
from ergplan.intake import iex_loader

RTM = """Date,Time Block,Hour,Session ID,Purchase Bid (MW),Sell Bid (MW),MCV (MW),Final Scheduled Volume (MW),MCP (₹/MWh)
2025-09-01,00:00-00:15,1,1,6963.7,16254.3,6871.85,6871.85,799.45
2025-09-01,00:15-00:30,1,1,7137.7,17052.5,7045.8,7045.8,799.95
2025-09-01,00:15-00:30,1,1,7137.7,17052.5,7045.8,7045.8,799.95
2025-09-02,23:45-24:00,24,48,1,1,1,1,"3,100.50"
"""

DAM = """Date,Time Block,Hour,Purchase Bid (MW),Sell Bid (MW),MCV (MW),Final Scheduled Volume (MW),MCP (₹/MWh),Scraped At
2025-09-01,00:00 - 00:15,1,5972.7,13098.6,3850.37,3850.37,2550.06,"15/9/2025, 6:49:34 am"
2025-09-01,00:00 - 00:15,1,5972.7,13098.6,3850.37,3850.37,2600.00,"16/9/2025, 6:49:34 am"
2025-09-01,00:15 - 00:30,1,5866,14059.5,3693.97,3693.97,2550.1,"15/9/2025, 6:49:34 am"
2025-09-01,bad,1,1,1,1,1,1,x
"""


def test_rtm_layout_by_session_column_and_exact_duplicates() -> None:
    p = iex_loader.parse(RTM.encode(), "prices.csv")
    assert p.segment == "rtm"
    assert [(r.day, r.block) for r in p.rows] == [
        (date(2025, 9, 1), 1),
        (date(2025, 9, 1), 2),
        (date(2025, 9, 2), 96),
    ]
    assert p.duplicates_dropped == 1 and p.conflicts == 0
    assert p.rows[2].mcp_inr_per_mwh == Decimal("3100.50")
    assert p.rows[0].mcv_mw == Decimal("6871.85")
    assert p.missing_blocks() == 2 * 96 - 3


def test_dam_conflict_keeps_latest_scrape_and_skips_bad_rows() -> None:
    p = iex_loader.parse(DAM.encode(), "DAM_15min.csv")
    assert p.segment == "dam"
    assert p.conflicts == 1
    assert p.rows[0].mcp_inr_per_mwh == Decimal("2600.00")
    assert p.skipped and "row 5" in p.skipped[0]


@pytest.mark.parametrize(
    ("name", "seg"),
    [
        ("GDAM_x.csv", "gdam"),
        ("iex-hpdam.csv", "hpdam"),
        ("G-TAM.csv", "gtam"),
        ("HP-DAM 2026.csv", "hpdam"),
        ("gtam 2025.xlsx", "gtam"),
        ("TAM.csv", "tam"),
        ("misc.csv", None),
    ],
)
def test_segment_from_name(name: str, seg: str | None) -> None:
    assert iex_loader.segment_from_name(name) == seg


def test_errors() -> None:
    with pytest.raises(iex_loader.PriceFileError, match="MCP"):
        iex_loader.parse(b"a,b\n1,2\n", "dam.csv")
    with pytest.raises(iex_loader.PriceFileError, match="segment"):
        iex_loader.parse(DAM.replace("Scraped At", "Note").encode(), "prices.csv")
    with pytest.raises(iex_loader.PriceFileError, match="no price rows"):
        iex_loader.parse(b"Date,Time Block,MCP\nx,y,z\n", "dam.csv")
    with pytest.raises(iex_loader.PriceFileError, match="workbook"):
        iex_loader.parse(b"not a zip", "dam.xlsx")


def test_store_overlap_replace_and_coverage() -> None:
    p = iex_loader.parse(RTM.encode(), "rtm.csv")
    with session_scope(actor="analyst@x") as s:
        v1 = iex_loader.store(s, p, "rtm.csv", "analyst@x")
        s.commit()
        again = iex_loader.store(s, p, "rtm.csv", "analyst@x")
        assert again.id == v1.id  # the same file is the same vintage
    p2 = iex_loader.parse(RTM.replace("799.45", "801.00").encode(), "rtm.csv")
    with session_scope(actor="analyst@x") as s:
        with pytest.raises(iex_loader.OverlappingVintage) as e:
            iex_loader.store(s, p2, "rtm2.csv", "analyst@x")
        assert e.value.vintage_ids == [v1.id]
        v2 = iex_loader.store(s, p2, "rtm2.csv", "analyst@x", replace=True)
        s.commit()
        assert s.get(PriceVintage, v1.id).superseded_by == v2.id  # type: ignore[union-attr]
        assert s.scalar(select(func.count()).select_from(PricePoint)) == 6  # old rows kept for replay
        cov = iex_loader.coverage(s, "rtm")
        assert [(c["day"], c["blocks"], c["vintage_id"]) for c in cov] == [
            ("2025-09-01", 2, v2.id),
            ("2025-09-02", 1, v2.id),
        ]


REAL = Path(__file__).resolve().parents[4] / "data" / "iex"


@pytest.mark.skipif(not REAL.exists() or not any(REAL.glob("*.xlsx")), reason="real IEX files not present")
@pytest.mark.parametrize("seg", ["RTM", "DAM"])
def test_real_file_per_segment(seg: str) -> None:
    f = next(REAL.glob(f"{seg}_*.xlsx"))
    p = iex_loader.parse(f.read_bytes(), f.name)
    assert p.segment == seg.lower()
    assert len(p.rows) > 30000
    assert all(1 <= r.block <= 96 for r in p.rows)
    assert all(Decimal(0) <= r.mcp_inr_per_mwh <= Decimal(20000) for r in p.rows)
