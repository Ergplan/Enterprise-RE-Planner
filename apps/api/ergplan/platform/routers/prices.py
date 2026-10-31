"""IEX price uploads (analyst): one vintage per file, coverage calendar per segment."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from ...db.base import session_scope
from ...db.models import PriceVintage
from ...intake import iex_loader
from ..auth import Caller, analyst

router = APIRouter(prefix="/prices", tags=["prices"])


class VintageOut(BaseModel):
    id: str
    segment: str
    filename: str
    file_sha256: str
    rows: int
    duplicates_dropped: int
    date_from: date
    date_to: date
    source_note: str | None
    uploaded_by: str
    uploaded_at: datetime | None
    superseded_by: str | None

    @classmethod
    def of(cls, v: PriceVintage) -> VintageOut:
        return cls(
            id=v.id,
            segment=v.segment,
            filename=v.filename,
            file_sha256=v.file_sha256,
            rows=v.rows,
            duplicates_dropped=v.duplicates_dropped,
            date_from=v.date_from,
            date_to=v.date_to,
            source_note=v.source_note,
            uploaded_by=v.uploaded_by,
            uploaded_at=v.uploaded_at,
            superseded_by=v.superseded_by,
        )


class UploadOut(BaseModel):
    vintage: VintageOut
    conflicts: int
    missing_blocks: int
    skipped: list[str]


@router.post("", response_model=UploadOut, status_code=201)
async def upload_prices(
    who: Annotated[Caller, Depends(analyst)],
    file: Annotated[UploadFile, File()],
    segment: Annotated[str | None, Form()] = None,
    replace: Annotated[bool, Form()] = False,
) -> UploadOut:
    data = await file.read()
    try:
        parsed = iex_loader.parse(data, file.filename or "prices.csv", segment)
    except iex_loader.PriceFileError as e:
        raise HTTPException(422, str(e)) from e
    with session_scope(actor=who.actor) as s:
        try:
            v = iex_loader.store(s, parsed, file.filename or "prices.csv", who.actor, replace=replace)
        except iex_loader.OverlappingVintage as e:
            raise HTTPException(409, {"message": str(e), "vintage_ids": e.vintage_ids}) from e
        out = UploadOut(
            vintage=VintageOut.of(v),
            conflicts=parsed.conflicts,
            missing_blocks=parsed.missing_blocks(),
            skipped=parsed.skipped,
        )
        s.commit()
        return out


@router.get("/vintages", response_model=list[VintageOut])
def vintages(segment: str | None = None) -> list[VintageOut]:
    with session_scope() as s:
        q = select(PriceVintage).order_by(PriceVintage.segment, PriceVintage.date_from)
        if segment:
            q = q.where(PriceVintage.segment == segment)
        return [VintageOut.of(v) for v in s.scalars(q)]


@router.get("/vintages/{vintage_id}", response_model=VintageOut)
def vintage(vintage_id: str) -> VintageOut:
    """The file a market price came from (a `market` source_ref resolves here)."""
    with session_scope() as s:
        v = s.get(PriceVintage, vintage_id)
        if v is None:
            raise HTTPException(404, "vintage not found")
        return VintageOut.of(v)


class CoverageDay(BaseModel):
    segment: str
    day: date
    blocks: int
    vintage_id: str


@router.get("/coverage", response_model=list[CoverageDay])
def coverage(segment: str | None = None) -> list[CoverageDay]:
    with session_scope() as s:
        return [CoverageDay.model_validate(c) for c in iex_loader.coverage(s, segment)]
