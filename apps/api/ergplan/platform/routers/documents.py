"""Documents: list, upload, open the PDF inline (so `#page=N` works), page images and text."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from ...db.base import session_scope
from ...db.models import SourceDocument
from ...documents import service

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: str
    title: str
    regulator: str | None
    jurisdiction: str | None
    document_kind: str
    utilities: list[str]
    file_sha256: str
    pages: int
    order_date: date | None
    effective_from: date | None
    url_public: str | None
    page_hints: dict[str, Any]
    notes: list[str]
    url: str

    @classmethod
    def of(cls, d: SourceDocument) -> DocumentOut:
        return cls(
            id=d.id,
            title=d.title,
            regulator=d.regulator,
            jurisdiction=d.jurisdiction,
            document_kind=d.document_kind,
            utilities=list(d.utilities or []),
            file_sha256=d.file_sha256,
            pages=d.pages,
            order_date=d.order_date,
            effective_from=d.effective_from,
            url_public=d.url_public,
            page_hints=dict(d.page_hints or {}),
            notes=list(d.notes or []),
            url=f"/documents/{d.id}",
        )


@router.get("", response_model=list[DocumentOut])
def list_documents(jurisdiction: str | None = None) -> list[DocumentOut]:
    with session_scope() as s:
        q = select(SourceDocument).order_by(SourceDocument.jurisdiction, SourceDocument.title)
        if jurisdiction:
            q = q.where(SourceDocument.jurisdiction == jurisdiction)
        return [DocumentOut.of(d) for d in s.scalars(q)]


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    regulator: Annotated[str | None, Form()] = None,
    jurisdiction: Annotated[str | None, Form()] = None,
    document_kind: Annotated[str, Form()] = "order",
    url_public: Annotated[str | None, Form()] = None,
    uploaded_by: Annotated[str, Form()] = "analyst",
) -> DocumentOut:
    data = await file.read()
    meta = service.DocumentMeta(
        title=title,
        regulator=regulator,
        jurisdiction=jurisdiction,
        document_kind=document_kind,
        url_public=url_public,
        original_filename=file.filename,
    )
    try:
        with session_scope(actor=uploaded_by) as s:
            doc, _ = service.register(s, data, meta, uploaded_by=uploaded_by)
            return DocumentOut.of(doc)
    except service.NotAPdf as e:
        raise HTTPException(422, str(e)) from e


@router.get("/{document_id}/meta", response_model=DocumentOut)
def document_meta(document_id: str) -> DocumentOut:
    with session_scope() as s:
        try:
            return DocumentOut.of(service.get(s, document_id))
        except service.DocumentNotFound as e:
            raise HTTPException(404, "document not found") from e


@router.get("/{document_id}")
def open_document(document_id: str) -> FileResponse:
    """The PDF, inline, so a browser honours `#page=N`."""
    with session_scope() as s:
        try:
            doc = service.get(s, document_id)
            path = service.file_path(doc)
        except service.DocumentNotFound as e:
            raise HTTPException(404, "document not found") from e
        name = (doc.original_filename or f"{doc.id}.pdf").replace('"', "")
    return FileResponse(
        path, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'}
    )


@router.get("/{document_id}/pages/{page}.png")
def page_image(document_id: str, page: int) -> Response:
    with session_scope() as s:
        try:
            doc = service.get(s, document_id)
            png = service.render_page_png(doc, page)
        except service.DocumentNotFound as e:
            raise HTTPException(404, "document not found") from e
        except service.PageOutOfRange as e:
            raise HTTPException(404, str(e)) from e
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/{document_id}/pages/{page}/text")
def page_text(document_id: str, page: int) -> dict[str, Any]:
    with session_scope() as s:
        try:
            doc = service.get(s, document_id)
            return {"document_id": doc.id, "page": page, "text": service.page_text(doc, page)}
        except service.DocumentNotFound as e:
            raise HTTPException(404, "document not found") from e
        except service.PageOutOfRange as e:
            raise HTTPException(404, str(e)) from e
