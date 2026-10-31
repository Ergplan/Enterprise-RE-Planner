"""Scanned pages: page_text falls back to stored OCR words when the text layer is empty."""

import shutil

import pytest

from ergplan.db.base import session_scope
from ergplan.documents import ocr, service
from tests.fixtures.pdfgen import make_pdf


def test_page_text_uses_stored_ocr_for_a_scanned_page() -> None:
    pdf = make_pdf([[""], ["A real text layer with enough characters to count as text"]])
    with session_scope(actor="t") as s:
        d, _ = service.register(s, pdf, service.DocumentMeta(title="scan"), "t")
        assert service.page_text(d, 1).strip() == "" and not service.page_is_ocr(d, 1)
        (ocr.ocr_dir(d.file_sha256) / "1.txt").write_text("Banking charges shall be 8% for Wind, Solar")
        assert service.page_text(d, 1) == "Banking charges shall be 8% for Wind, Solar"
        assert service.page_is_ocr(d, 1)
        assert "real text layer" in service.page_text(d, 2)  # a page with a text layer never uses OCR


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_ocr_document_reads_only_scanned_pages() -> None:
    pdf = make_pdf([[""], ["Another real text layer, long enough to count as a text page"]])
    with session_scope(actor="t") as s:
        d, _ = service.register(s, pdf, service.DocumentMeta(title="scan2"), "t")
        assert ocr.ocr_document(d, service.file_path(d)) == 1  # page 1 only
        assert ocr.ocr_text(d.file_sha256, 1) is not None and ocr.ocr_text(d.file_sha256, 2) is None
