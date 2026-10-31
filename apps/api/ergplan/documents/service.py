"""Source PDFs: stored once by SHA-256 under data/documents/<sha>.pdf, one row each, pages rendered
on demand. The only writer of source_documents."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..db.models import SourceDocument


class NotAPdf(ValueError):
    pass


class DocumentNotFound(LookupError):
    pass


class PageOutOfRange(LookupError):
    pass


@dataclass(frozen=True)
class DocumentMeta:
    title: str
    regulator: str | None = None
    jurisdiction: str | None = None
    document_kind: str = "order"
    utilities: tuple[str, ...] = ()
    order_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    url_public: str | None = None
    notes: tuple[str, ...] = ()
    page_hints: dict[str, Any] | None = None
    original_filename: str | None = None


def documents_dir() -> Path:
    d = get_settings().documents_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def path_for(sha256: str) -> Path:
    return documents_dir() / f"{sha256}.pdf"


def page_count(data: bytes) -> int:
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(data))
    except pdfium.PdfiumError as e:
        raise NotAPdf("the file is not a readable PDF") from e
    try:
        return len(pdf)
    finally:
        pdf.close()


def register(
    session: Session, data: bytes, meta: DocumentMeta, uploaded_by: str
) -> tuple[SourceDocument, bool]:
    """Store the PDF and its row. Returns (document, created). Same bytes → the existing row."""
    if not data.startswith(b"%PDF"):
        raise NotAPdf("the file does not start with %PDF")
    sha = hashlib.sha256(data).hexdigest()
    existing = session.scalar(select(SourceDocument).where(SourceDocument.file_sha256 == sha))
    if existing is not None:
        return existing, False
    pages = page_count(data)
    target = path_for(sha)
    if not target.exists():
        tmp = target.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(target)
    doc = SourceDocument(
        title=meta.title,
        regulator=meta.regulator,
        jurisdiction=meta.jurisdiction,
        document_kind=meta.document_kind,
        utilities=list(meta.utilities),
        file_sha256=sha,
        file_bytes=len(data),
        pages=pages,
        order_date=meta.order_date,
        effective_from=meta.effective_from,
        effective_to=meta.effective_to,
        url_public=meta.url_public,
        notes=list(meta.notes),
        page_hints=meta.page_hints or {},
        original_filename=meta.original_filename,
        uploaded_by=uploaded_by,
    )
    session.add(doc)
    session.flush()
    return doc, True


def get(session: Session, document_id: str) -> SourceDocument:
    doc = session.get(SourceDocument, document_id)
    if doc is None:
        raise DocumentNotFound(document_id)
    return doc


def file_path(doc: SourceDocument) -> Path:
    p = path_for(doc.file_sha256)
    if not p.exists():
        raise DocumentNotFound(f"file for {doc.id} is missing from the store")
    return p


def render_page_png(doc: SourceDocument, page: int, scale: float = 1.5) -> bytes:
    """Render a 1-based page to PNG bytes."""
    if page < 1 or page > doc.pages:
        raise PageOutOfRange(f"page {page} is outside 1..{doc.pages}")
    pdf = pdfium.PdfDocument(str(file_path(doc)))
    try:
        bitmap = pdf[page - 1].render(scale=scale)
        img = bitmap.to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        pdf.close()


def page_text(doc: SourceDocument, page: int) -> str:
    """The text layer of a 1-based page ('' when the page is a scan)."""
    if page < 1 or page > doc.pages:
        raise PageOutOfRange(f"page {page} is outside 1..{doc.pages}")
    pdf = pdfium.PdfDocument(str(file_path(doc)))
    try:
        tp = pdf[page - 1].get_textpage()
        return str(tp.get_text_range())
    finally:
        pdf.close()
