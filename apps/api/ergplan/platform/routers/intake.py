"""Intake: bills through billx, one-click confirmations, the site form, load profiles.

Client endpoints (no analyst role needed until Stage 8 adds sessions). Numbers about the client's
load are returned as SourcedValues whose refs point at the bill field, the client's statement or
ergPLAN's assumption they came from.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...core.settings import get_settings
from ...core.sourced import RefKind, SourcedValue, SourceRef
from ...core.units import Unit
from ...db.base import session_scope
from ...db.models import Bill, Client, Connection, LoadProfile, Site
from ...intake import bills as bill_store
from ...intake import defaults, measured_upload, profile_synthesis, site_intake
from ...intake.billx_client import BillxError, BillxUnavailable
from ..auth import Caller, caller, owned_bills, owned_connection

router = APIRouter(tags=["intake"])


class FieldReviewOut(BaseModel):
    path: str
    value: str | None
    unit: str | None
    verification: str | None
    page: int | None
    required: bool
    confirmed: bool
    needs_confirmation: bool


class BillOut(BaseModel):
    id: str
    filename: str | None
    bill_index: int
    bill_month: date | None
    status: str
    accepted: bool
    accepted_by: str | None
    discom: str | None
    connection_id: str | None
    review_reasons: list[str]
    fields: list[FieldReviewOut]
    outstanding: list[str]
    tod_slots: list[str | None]
    file_url: str


def _bill_out(s: Any, b: Bill) -> BillOut:
    rv = bill_store.review(s, b)
    facts = bill_store._bill_facts(b)
    return BillOut(
        id=b.id,
        filename=b.filename,
        bill_index=b.bill_index,
        bill_month=b.bill_month,
        status=b.status,
        accepted=b.accepted,
        accepted_by=b.accepted_by,
        discom=defaults.discom_from_profile(facts.profile_id),
        connection_id=b.connection_id,
        review_reasons=facts.review_reasons,
        fields=[FieldReviewOut(**r.as_json()) for r in rv],
        outstanding=[r.path for r in rv if r.needs_confirmation],
        tod_slots=bill_store.tod_slots(b),
        file_url=f"/bills/{b.id}/file",
    )


@router.post("/bills", response_model=list[BillOut], status_code=201)
async def upload_bill(
    file: Annotated[UploadFile, File()],
    who: Annotated[Caller, Depends(caller)],
    connection_id: Annotated[str | None, Form()] = None,
) -> list[BillOut]:
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "a bill is uploaded as a PDF")
    try:
        with session_scope() as s:
            if connection_id and s.get(Connection, connection_id) is None:
                raise HTTPException(404, "connection not found")
            owned_connection(s, who, connection_id)
            rows = bill_store.ingest(
                s,
                data,
                file.filename or "bill.pdf",
                connection_id=connection_id,
                uploaded_by=who.actor if who.signed_in else None,
            )
            out = [_bill_out(s, b) for b in rows]
            s.commit()
            return out
    except BillxUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except BillxError as e:
        raise HTTPException(502, str(e)) from e


def _get_bill(s: Any, bill_id: str) -> Bill:
    b = s.get(Bill, bill_id)
    if b is None:
        raise HTTPException(404, "bill not found")
    return b  # type: ignore[no-any-return]


@router.get("/bills/{bill_id}", response_model=BillOut)
def get_bill(bill_id: str) -> BillOut:
    with session_scope() as s:
        return _bill_out(s, _get_bill(s, bill_id))


@router.get("/bills/{bill_id}/file")
def bill_file(bill_id: str) -> FileResponse:
    with session_scope() as s:
        sha = _get_bill(s, bill_id).file_sha256
    p = get_settings().bill_files_dir / f"{sha}.pdf"
    if not p.exists():
        raise HTTPException(404, "the bill file is not stored")
    return FileResponse(p, media_type="application/pdf", headers={"Content-Disposition": "inline"})


class ConfirmIn(BaseModel):
    path: str
    value: str | None = Field(default=None, max_length=200)


@router.post("/bills/{bill_id}/confirm", response_model=BillOut)
def confirm_field(bill_id: str, body: ConfirmIn, who: Annotated[Caller, Depends(caller)]) -> BillOut:
    with session_scope() as s:
        _get_bill(s, bill_id)
        try:
            b = bill_store.confirm(s, bill_id, body.path, body.value, who.actor)
        except bill_store.UnknownField as e:
            raise HTTPException(422, f"no such field on this bill: {e}") from e
        out = _bill_out(s, b)
        s.commit()
        return out


class ShapeOut(BaseModel):
    id: str
    name: str
    note: str | None
    working_days: list[int]


@router.get("/intake/shapes", response_model=list[ShapeOut])
def shapes() -> list[ShapeOut]:
    out = []
    for sid in profile_synthesis.shape_ids():
        _, d = profile_synthesis.shape(sid)
        out.append(
            ShapeOut(
                id=sid,
                name=d.get("name", sid),
                note=d.get("note"),
                working_days=profile_synthesis.working_days(sid),
            )
        )
    return out


class FromBillsIn(BaseModel):
    bill_ids: list[str] = Field(min_length=1, max_length=24)
    overrides: dict[str, Any] = Field(default_factory=dict)


@router.post("/intake/from-bills", response_model=site_intake.SiteIntake)
def intake_from_bills(body: FromBillsIn, who: Annotated[Caller, Depends(caller)]) -> site_intake.SiteIntake:
    with session_scope() as s:
        owned_bills(s, who, body.bill_ids)
        try:
            return site_intake.from_bills(s, body.bill_ids, body.overrides)
        except bill_store.BillNotFound as e:
            raise HTTPException(404, f"bill not found: {e}") from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e


class BuildIn(BaseModel):
    intake: site_intake.SiteIntake
    connection_id: str | None = None


class BuildOut(BaseModel):
    client_id: str
    site_id: str
    connection_id: str
    load_profile_id: str
    load_profile_version: int
    warnings: list[str]


@router.post("/sites", response_model=BuildOut, status_code=201)
def build_site(body: BuildIn, who: Annotated[Caller, Depends(caller)]) -> BuildOut:
    with session_scope() as s:
        owned_connection(s, who, body.connection_id)
        try:
            out = site_intake.build(s, body.intake, who.actor, connection_id=body.connection_id)
        except LookupError as e:
            raise HTTPException(404, f"connection not found: {e}") from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        s.commit()
        return BuildOut(**out)


class ProfileMonth(BaseModel):
    month: date
    energy_kwh: SourcedValue = Field(
        json_schema_extra={
            "owner": "load_profiles.series_kw + load_profiles.method",
            "ref_kinds": ["bill", "client_stated", "assumption", "measured"],
        }
    )
    max_kw: SourcedValue = Field(
        json_schema_extra={
            "owner": "load_profiles.series_kw + load_profiles.method",
            "ref_kinds": ["bill", "client_stated", "assumption", "measured"],
        }
    )
    extrapolated: bool
    peak_shortfall_kw: str | None = None


class ProfileOut(BaseModel):
    id: str
    connection_id: str
    version: int
    provenance: str
    year_start: date
    blocks: int
    method: dict[str, Any]
    months: list[ProfileMonth]
    week_kw: list[str]  # the first full week of the busiest month, for the chart


class ConnectionOut(BaseModel):
    id: str
    client: dict[str, Any]
    site: dict[str, Any]
    discom_id: str
    tariff_category: str | None
    voltage_kv: str | None
    contract_demand_kva: str | None
    connection_kind: str
    provenance: dict[str, Any]
    bills: list[dict[str, Any]]
    profiles: list[dict[str, Any]]


@router.get("/connections/{connection_id}", response_model=ConnectionOut)
def get_connection(connection_id: str) -> ConnectionOut:
    with session_scope() as s:
        c = s.get(Connection, connection_id)
        if c is None:
            raise HTTPException(404, "connection not found")
        site = s.get(Site, c.site_id)
        assert site is not None
        client = s.get(Client, site.client_id)
        assert client is not None
        bills = s.scalars(select(Bill).where(Bill.connection_id == c.id).order_by(Bill.bill_month)).all()
        profs = s.scalars(
            select(LoadProfile).where(LoadProfile.connection_id == c.id).order_by(LoadProfile.version)
        ).all()
        return ConnectionOut(
            id=c.id,
            client={"id": client.id, "name": client.name},
            site={
                "id": site.id,
                "name": site.name,
                "state": site.state,
                "industry_shape": site.industry_shape,
                "weekly_off": site.weekly_off,
                "provenance": site.provenance,
            },
            discom_id=c.discom_id,
            tariff_category=c.tariff_category,
            voltage_kv=None if c.voltage_kv is None else format(c.voltage_kv, "f"),
            contract_demand_kva=None if c.contract_demand_kva is None else format(c.contract_demand_kva, "f"),
            connection_kind=c.connection_kind,
            provenance=c.provenance,
            bills=[
                {"id": b.id, "bill_month": b.bill_month, "status": b.status, "accepted": b.accepted}
                for b in bills
            ],
            profiles=[
                {"id": p.id, "version": p.version, "provenance": p.provenance, "created_at": p.created_at}
                for p in profs
            ],
        )


@router.get("/connections/{connection_id}/intake", response_model=site_intake.SiteIntake)
def get_intake(connection_id: str) -> site_intake.SiteIntake:
    """The intake the latest synthesised profile was built from, for step 4 to edit and rebuild."""
    with session_scope() as s:
        p = s.scalars(
            select(LoadProfile)
            .where(LoadProfile.connection_id == connection_id, LoadProfile.provenance == "synthesised")
            .order_by(LoadProfile.version.desc())
        ).first()
        if p is None or "intake" not in p.method:
            raise HTTPException(404, "no intake recorded for this connection")
        return site_intake.SiteIntake.model_validate(p.method["intake"])


def _refs(entry: dict[str, Any] | None, fallback: str) -> tuple[SourceRef, ...]:
    if entry and entry.get("source_ref"):
        d = {k: v for k, v in entry["source_ref"].items() if k != "url"}
        return (SourceRef.model_validate(d),)
    return (SourceRef(kind=RefKind.ASSUMPTION, note=fallback),)


def _profile_out(p: LoadProfile) -> ProfileOut:
    kw = profile_synthesis.decode(p.series_kw)
    days = profile_synthesis.year_days(p.year_start)
    months: list[ProfileMonth] = []
    inputs = {m["month"]: m for m in (p.method.get("inputs") or {}).get("months", [])}
    reports = {r["month"]: r for r in p.method.get("months", [])}
    i = 0
    best: tuple[bool, Decimal, int] = (False, Decimal(-1), 0)  # prefer a billed month for the chart
    for m in range(12):
        y, mo = p.year_start.year + (p.year_start.month - 1 + m) // 12, (p.year_start.month - 1 + m) % 12 + 1
        first = date(y, mo, 1)
        n = sum(1 for d in days if d.year == y and d.month == mo) * 96
        seg = kw[i : i + n]
        energy = (sum(seg, Decimal(0)) * Decimal("0.25")).quantize(Decimal("0.001"))
        peak = max(seg) if seg else Decimal(0)
        billed = p.provenance == "measured" or not reports.get(first.isoformat(), {}).get("extrapolated")
        if (billed, energy) > best[:2]:
            best = (billed, energy, i)
        rep = reports.get(first.isoformat(), {})
        if p.provenance == "measured":
            # measured_upload.store records the meter file name under method["file"]
            mref: tuple[SourceRef, ...] = (
                SourceRef(kind=RefKind.MEASURED, note=f"meter file {p.method.get('file')}"),
            )
            eref, pref = mref, mref
        else:
            src = inputs.get(rep.get("from_bill_month", "")) or inputs.get(first.isoformat())
            if rep.get("extrapolated"):
                eref = (
                    SourceRef(
                        kind=RefKind.ASSUMPTION,
                        note="no bill for this month: mean daily energy of the billed months",
                    ),
                )
                pref = eref
            else:
                eref = _refs(src.get("energy") if src else None, "month energy")
                if src and src.get("energy_unit") == "kVAh":
                    pf_note = (
                        "the bill's power factor"
                        if src.get("power_factor")
                        else "a power factor of 0.95 (assumed)"
                    )
                    eref = (
                        *eref,
                        SourceRef(
                            kind=RefKind.ASSUMPTION, note=f"billed in kVAh; converted to kWh with {pf_note}"
                        ),
                    )
                pref = eref + tuple(
                    r
                    for k in ("max_kva", "power_factor")
                    for r in _refs(
                        src.get(k) if src else None, f"{k} not given: peak follows the industry shape"
                    )
                )
        months.append(
            ProfileMonth(
                month=first,
                extrapolated=bool(rep.get("extrapolated")),
                energy_kwh=SourcedValue(value=energy, unit=Unit.KWH, source_refs=eref),
                max_kw=SourcedValue(value=peak, unit=Unit.KW, source_refs=tuple(dict.fromkeys(pref))),
                peak_shortfall_kw=None
                if rep.get("peak_shortfall_kw") is None
                else str(rep["peak_shortfall_kw"]),
            )
        )
        i += n
    start = best[2]
    week = [f"{v:.1f}" for v in kw[start : start + 7 * 96]]
    return ProfileOut(
        id=p.id,
        connection_id=p.connection_id,
        version=p.version,
        provenance=p.provenance,
        year_start=p.year_start,
        blocks=p.blocks,
        method=p.method,
        months=months,
        week_kw=week,
    )


def _profile(s: Any, connection_id: str, version: int | None) -> LoadProfile:
    q = select(LoadProfile).where(LoadProfile.connection_id == connection_id)
    q = q.where(LoadProfile.version == version) if version else q.order_by(LoadProfile.version.desc())
    p = s.scalars(q).first()
    if p is None:
        raise HTTPException(404, "no load profile for this connection")
    return p  # type: ignore[no-any-return]


@router.get("/connections/{connection_id}/profile", response_model=ProfileOut)
def get_profile(connection_id: str, version: int | None = None) -> ProfileOut:
    with session_scope() as s:
        return _profile_out(_profile(s, connection_id, version))


@router.get("/connections/{connection_id}/profile.csv", response_class=PlainTextResponse)
def profile_csv(connection_id: str, version: int | None = None) -> str:
    with session_scope() as s:
        p = _profile(s, connection_id, version)
        vals = profile_synthesis.decode(p.series_kw)
        days = profile_synthesis.year_days(p.year_start)
        lines = ["day,block,kw"] + [f"{days[i // 96]},{i % 96 + 1},{v}" for i, v in enumerate(vals)]
        return "\n".join(lines) + "\n"


@router.post("/connections/{connection_id}/profile/measured", response_model=ProfileOut, status_code=201)
async def upload_measured(
    connection_id: str, file: Annotated[UploadFile, File()], year_start: Annotated[date | None, Form()] = None
) -> ProfileOut:
    data = await file.read()
    try:
        m = measured_upload.parse(data, year_start)
    except measured_upload.MeasuredFileError as e:
        raise HTTPException(422, str(e)) from e
    with session_scope() as s:
        if s.get(Connection, connection_id) is None:
            raise HTTPException(404, "connection not found")
        lp = measured_upload.store(
            s, connection_id, m, file.filename or "meter.csv", hashlib.sha256(data).hexdigest()
        )
        out = _profile_out(lp)
        s.commit()
        return out
