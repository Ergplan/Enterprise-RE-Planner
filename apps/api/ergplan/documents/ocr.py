"""OCR for scanned regulation pages (tesseract). The words are stored beside the PDF as
data/ocr/<sha256>/<page>.txt and served by documents.service.page_text when a page has no text
layer, so the reader's grounding check and every citation work on scanned orders too. A page
read by OCR is marked as such wherever its text is shown."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pypdfium2 as pdfium

from ..core.settings import get_settings
from ..db.models import SourceDocument

MIN_TEXT_CHARS = 40  # a page with fewer characters in its text layer is treated as a scan


def ocr_dir(sha256: str) -> Path:
    d = get_settings().ergplan_data_dir / "ocr" / sha256
    d.mkdir(parents=True, exist_ok=True)
    return d


def ocr_text(sha256: str, page: int) -> str | None:
    p = get_settings().ergplan_data_dir / "ocr" / sha256 / f"{page}.txt"
    return p.read_text() if p.exists() else None


def available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_document(
    doc: SourceDocument, pdf_path: Path, pages: list[int] | None = None, scale: float = 3.0
) -> int:
    """OCR the pages that have no usable text layer (or the pages given). Returns pages written."""
    if not available():
        raise RuntimeError("tesseract is not installed")
    out = ocr_dir(doc.file_sha256)
    pdf = pdfium.PdfDocument(str(pdf_path))
    written = 0
    try:
        for n in pages or range(1, len(pdf) + 1):
            target = out / f"{n}.txt"
            if target.exists():
                continue
            page = pdf[n - 1]
            if pages is None and len(page.get_textpage().get_text_range().strip()) >= MIN_TEXT_CHARS:
                continue
            img = out / f"{n}.png"
            page.render(scale=scale).to_pil().convert("L").save(img)
            r = subprocess.run(
                ["tesseract", str(img), "stdout", "-l", "eng", "--psm", "6"],
                capture_output=True,
                text=True,
                check=False,
            )
            img.unlink(missing_ok=True)
            target.write_text(r.stdout)
            written += 1
    finally:
        pdf.close()
    return written
