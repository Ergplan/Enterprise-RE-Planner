"""The direct regulation reader: pages of a stored PDF → candidate rule rows (OpenAI, through
providers) → grounding checks → schema validation → accepted rows ready for a draft version.
It never approves anything; a person reviews the draft beside the page."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ..db.models import SourceDocument
from ..documents import service as documents
from ..providers.openai_client import CallResult, call_json
from ..rulebook.schemas import family_schema, scope_schema, validate_row
from .grounding import quote_on_page, semantic_numbers, ungrounded_numbers

PAGES_PER_CALL = 4
PROMPT_VERSION = 2


@dataclass
class Rejected:
    row: dict[str, Any]
    reasons: list[str]


@dataclass
class ReadResult:
    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0


def _schemas_for_prompt(family: str) -> str:
    return json.dumps(
        {"scope": scope_schema(), "body": family_schema(family)["properties"]["body"]}, indent=1
    )


def build_user_prompt(
    doc: SourceDocument, family: str, jurisdiction_id: str, pages: dict[int, str], focus: str
) -> str:
    parts = [
        f"Document: {doc.title} ({doc.regulator}, {doc.jurisdiction}, order date {doc.order_date})",
        f"Jurisdiction for these rows: {jurisdiction_id}",
        f"Rule family: {family}",
        f"Focus: {focus or 'everything of this family on these pages'}",
        "JSON Schemas:",
        _schemas_for_prompt(family),
        "Pages:",
    ]
    for n, t in sorted(pages.items()):
        parts.append(f"=== PDF page {n} ===\n{t}")
    return "\n\n".join(parts)


def check_row(
    family: str,
    cand: dict[str, Any],
    pages: dict[int, str],
    doc: SourceDocument,
    ocr_pages: frozenset[int] = frozenset(),
) -> tuple[dict[str, Any] | None, list[str]]:
    """Grounding and schema checks. Returns (row ready for the rulebook, []) or (None, reasons)."""
    reasons: list[str] = []
    page = cand.get("page")
    quote = str(cand.get("quote") or "")
    if not isinstance(page, int) or page not in pages:
        return None, [f"cited page {page} was not among the pages read"]
    if not quote_on_page(quote, pages[page], ocr=page in ocr_pages):
        reasons.append(f"quote not found on page {page}")
    field_refs: dict[str, Any] = {}
    cited_texts = [pages[page]]
    for pointer, fq in (cand.get("field_quotes") or {}).items():
        fp, fqt = fq.get("page"), str(fq.get("quote") or "")
        if fp not in pages or not quote_on_page(fqt, pages[fp], ocr=fp in ocr_pages):
            reasons.append(f"field quote for {pointer} not found on page {fp}")
            continue
        cited_texts.append(pages[fp])
        field_refs[pointer.removeprefix("/body")] = {
            "kind": "regulation" if doc.document_kind == "regulation" else "order",
            "document_id": doc.id,
            "page": fp,
            "quote": fqt[:400],
        }
    body = cand.get("body") or {}
    missing = ungrounded_numbers(semantic_numbers(body, cited_texts), cited_texts)
    if missing:
        reasons.append(f"numbers not printed on the cited pages: {', '.join(missing)}")
    kind = "regulation" if doc.document_kind == "regulation" else "order"
    ref: dict[str, Any] = {"kind": kind, "document_id": doc.id, "page": page, "quote": quote[:400]}
    if page in ocr_pages:
        ref["note"] = "page text read by OCR"
    if doc.effective_from:
        ref["effective_from"] = doc.effective_from.isoformat()
    row: dict[str, Any] = {
        "label": cand.get("label"),
        "scope": cand.get("scope") or {},
        "body": body,
        "source_ref": ref,
    }
    if field_refs:
        row["field_refs"] = field_refs
    row = {k: v for k, v in row.items() if v is not None}
    errors = validate_row(family, row)
    reasons += [f"schema: {e}" for e in errors]
    return (None, reasons) if reasons else (row, [])


def read(
    session: Session,
    *,
    document_id: str,
    family: str,
    jurisdiction_id: str,
    pages: list[int],
    focus: str = "",
    model: str | None = None,
    pages_per_call: int = PAGES_PER_CALL,
) -> ReadResult:
    """Read the pages in groups of `pages_per_call` (a regulation that spans pages needs them in one call)."""
    doc = documents.get(session, document_id)
    texts = {p: documents.page_text(doc, p) for p in sorted(set(pages))}
    ocr_pages = frozenset(p for p in texts if documents.page_is_ocr(doc, p))
    result = ReadResult()
    ordered = sorted(texts)
    for i in range(0, len(ordered), pages_per_call):
        chunk = {p: texts[p] for p in ordered[i : i + pages_per_call]}
        if not any(t.strip() for t in chunk.values()):
            result.notes.append(f"pages {list(chunk)} have no text layer (scanned); not read")
            continue
        r: CallResult = call_json(
            prompt_name=f"regreader_{family}",
            prompt_version=PROMPT_VERSION,
            purpose="regreader_direct",
            user=build_user_prompt(doc, family, jurisdiction_id, chunk, focus),
            model=model,
            ref_type="source_document",
            ref_id=doc.id,
        )
        result.calls.append(r.call_id)
        result.tokens_in += r.tokens_in
        result.tokens_out += r.tokens_out
        result.not_found += [str(x) for x in r.data.get("not_found") or []]
        if r.data.get("notes"):
            result.notes.append(str(r.data["notes"]))
        for cand in r.data.get("rows") or []:
            row, reasons = check_row(family, cand, texts, doc, ocr_pages)
            if row is None:
                result.rejected.append(Rejected(cand, reasons))
            else:
                row["review"] = {
                    "reader": "regreader_direct",
                    "model": r.model,
                    "prompt": r.prompt,
                    "call_id": r.call_id,
                    "decision": "proposed",
                }
                result.accepted.append(row)
    return result
