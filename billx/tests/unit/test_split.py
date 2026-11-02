"""Page sorting (5.0): several bills in one file become several bills."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from billx.reader.identify.split import group_pages, signals


def test_signals_read_page_of_bill_number_and_date():
    s = signals(1, "Bill No. 900000000326 Bill Month Mar-2026 Bill Dafe 05-Mar-2026 Page 1 of 2")
    assert s.page_of == (1, 2)
    assert s.bill_no == "900000000326"
    assert s.bill_date == "2026-03-05"


def test_two_bills_of_two_pages_each_are_split_on_their_page_markers():
    texts = [
        "Bill No. 900000000326 Bill Date 05-Mar-2026 Page 1 of 2",
        "CALCULATIONS Bill Date : 05-Mar-2026 Page 2 of 2",
        "Bill No. 900000000226 Bill Date 05-Feb-2026 Page 1 of 2",
        "CALCULATIONS Bill Date : 05-Feb-2026 Page 2 of 2",
    ]
    assert group_pages(texts) == [(1, 2), (3, 4)]


def test_a_new_bill_number_or_date_starts_a_bill_without_page_markers():
    texts = ["Bill No: A123456 Bill Date 01-01-2026", "Bill No: B999999 Bill Date 01-02-2026"]
    assert group_pages(texts) == [(1,), (2,)]
    texts = ["Bill Date 01-01-2026 energy", "Bill Date 01-02-2026 energy"]
    assert group_pages(texts) == [(1,), (2,)]


def test_one_misread_character_in_a_repeated_bill_number_never_splits_a_bill():
    texts = ["Bill No. 900000000326 consumption", "Bill No. 900000000328 charges"]
    assert group_pages(texts) == [(1, 2)]


def test_a_continuation_page_never_starts_a_bill_even_with_another_date():
    # a misread date on page 2 of 2 must not split the bill
    texts = ["Bill Date 05-Mar-2026 Page 1 of 2", "Bill Date 06-Mar-2026 Page 2 of 2"]
    assert group_pages(texts) == [(1, 2)]


def test_pages_without_signals_stay_one_bill():
    assert group_pages(["tariff kWh", "meter reading", "total"]) == [(1, 2, 3)]
    assert group_pages([]) == [()]


@pytest.mark.ocr
def test_a_file_of_two_synthetic_bills_reads_as_two_bills(tmp_path: Path):
    from billx.platform.api.examples import ReplayModel
    from billx.platform.synth.cli import build
    from billx.reader.pipeline import read_file

    out = tmp_path / "synth"
    build(out, 1)
    files = sorted(p for p in out.glob("*.digital.pdf") if p.name.startswith("pvvnl"))[:2]
    assert len(files) == 2
    merged = pdfium.PdfDocument.new()
    counts = []
    for f in files:
        src = pdfium.PdfDocument(f.read_bytes())
        counts.append(len(src))
        merged.import_pages(src)
    both = tmp_path / "two-bills.pdf"
    merged.save(str(both))
    a, b = ReplayModel.pair(files)
    env = read_file(both, allow_cloud_model=True, max_cost_usd=Decimal("1"), model_a=a, model_b=b)
    assert [bill.index for bill in env.bills] == [0, 1]
    assert env.bills[0].pages == tuple(range(1, counts[0] + 1))
    assert env.bills[1].pages == tuple(range(counts[0] + 1, counts[0] + counts[1] + 1))
