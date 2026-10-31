"""The two doors into a draft rulebook: the direct reader (OpenAI over stored pages, grounded) and
the tariff-oder import. Both write drafts only; approval is the rulebook endpoints' job."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.settings import get_settings
from ...db.base import session_scope
from ...documents import service as documents
from ...providers.openai_client import NoModelConfigured, ProviderError
from ...regreader import direct, locate, tariff_oder
from ...rulebook import service
from ..auth import Caller, analyst

router = APIRouter(prefix="/regreader", tags=["regreader"])
Analyst = Annotated[Caller, Depends(analyst)]


class DirectIn(BaseModel):
    document_id: str
    family: str
    jurisdiction_id: str
    pages: list[int]
    focus: str = ""
    effective_from: date | None = None
    title: str | None = None


class DraftOut(BaseModel):
    version_id: str | None
    family: str
    accepted: int
    rejected: list[dict[str, Any]]
    not_found: list[str]
    notes: list[str]
    tokens_in: int = 0
    tokens_out: int = 0


@router.get("/locate/{document_id}")
def locate_pages(
    document_id: str, topic: str, lo: int | None = None, hi: int | None = None
) -> dict[str, Any]:
    with session_scope() as s:
        try:
            doc = documents.get(s, document_id)
        except documents.DocumentNotFound as e:
            raise HTTPException(404, "document not found") from e
        hits = locate.locate(doc, topic, (lo, hi) if lo and hi else None)
        return {
            "document_id": document_id,
            "topic": topic,
            "pages": [{"page": p, "hits": n} for p, n in hits],
        }


@router.post("/direct", response_model=DraftOut, status_code=201)
def read_direct(body: DirectIn, who: Analyst) -> DraftOut:
    if not body.pages or len(body.pages) > 24:
        raise HTTPException(422, "read between 1 and 24 pages at a time")
    try:
        with session_scope() as s:
            doc = documents.get(s, body.document_id)
            eff = body.effective_from or doc.effective_from or doc.order_date
            title = body.title or f"{doc.title} · pages {min(body.pages)}–{max(body.pages)}"
            r = direct.read(
                s,
                document_id=doc.id,
                family=body.family,
                jurisdiction_id=body.jurisdiction_id,
                pages=body.pages,
                focus=body.focus,
            )
    except documents.DocumentNotFound as e:
        raise HTTPException(404, "document not found") from e
    except NoModelConfigured as e:
        raise HTTPException(503, str(e)) from e
    except ProviderError as e:
        raise HTTPException(502, str(e)) from e
    vid = None
    if r.accepted:
        if eff is None:
            raise HTTPException(422, "the document has no order date; pass effective_from")
        with session_scope(actor=who.actor, role=who.role) as s:
            v = service.propose(
                s,
                family=body.family,
                jurisdiction_id=body.jurisdiction_id,
                rows=r.accepted,
                actor=who.actor,
                effective_from=eff,
                title=title,
                origin="regreader_direct",
                notes=f"focus: {body.focus}; calls: {', '.join(r.calls)}",
            )
            vid = v.id
    return DraftOut(
        version_id=vid,
        family=body.family,
        accepted=len(r.accepted),
        rejected=[{"row": x.row, "reasons": x.reasons} for x in r.rejected],
        not_found=r.not_found,
        notes=r.notes,
        tokens_in=r.tokens_in,
        tokens_out=r.tokens_out,
    )


class TariffOderIn(BaseModel):
    document_id: str
    jurisdiction_id: str
    source_id: str | None = None  # read live from TARIFF_ODER_URL
    tariff: dict[str, Any] | None = None  # or pass the explorer JSON (from an export)
    network: dict[str, Any] | None = None
    effective_from: date | None = None


@router.post("/tariff-oder", response_model=list[DraftOut], status_code=201)
def import_tariff_oder(body: TariffOderIn, who: Analyst) -> list[DraftOut]:
    tariff, network = body.tariff, body.network
    if body.source_id:
        st = get_settings()
        if not st.tariff_oder_url:
            raise HTTPException(503, "TARIFF_ODER_URL is not set")
        client = tariff_oder.TariffOderClient(st.tariff_oder_url, st.tariff_oder_token)
        tariff, network = client.tariff(body.source_id), client.network(body.source_id)
    if tariff is None and network is None:
        raise HTTPException(422, "give a source_id or the explorer JSON")
    with session_scope() as s:
        doc = documents.get(s, body.document_id)
        eff = body.effective_from or doc.effective_from or doc.order_date
    m = tariff_oder.map_facts(
        tariff_oder.facts_from_explorer(tariff, network),
        document_id=body.document_id,
        effective_from=eff.isoformat() if eff else None,
    )
    out = []
    for family, rows in m.by_family.items():
        if not rows:
            continue
        with session_scope(actor=who.actor, role=who.role) as s:
            v = service.propose(
                s,
                family=family,
                jurisdiction_id=body.jurisdiction_id,
                rows=rows,
                actor=who.actor,
                effective_from=eff or date.today(),
                title=f"tariff-oder import · {doc.title}",
                origin="tariff_oder",
                notes=f"{m.facts_read} facts read",
            )
            out.append(
                DraftOut(
                    version_id=v.id, family=family, accepted=len(rows), rejected=[], not_found=[], notes=[]
                )
            )
    out.append(
        DraftOut(
            version_id=None,
            family="unmapped",
            accepted=0,
            rejected=[
                {"row": {"fact_id": u.fact_id, "family": u.family}, "reasons": [u.reason]} for u in m.unmapped
            ],
            not_found=[],
            notes=[],
        )
    )
    return out
