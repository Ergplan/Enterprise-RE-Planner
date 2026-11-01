"""Search and analytics over stored bills.

Search: every bill a person may see becomes one Haystack `Document` (its DISCOM, consumer,
month, category, every value billx read with its label, the time-of-day slots, the printed charge
lines, the checks), ranked by BM25 against the question; each hit names the lines that matched
and links to the reading view. No model is called: retrieval is keyword ranking (invariant 4).

Analytics: per account and month, the figures planning cares about (consumption by slot, open
access set off, billed units, demand, power factor, charges), read from billx's stored result
and returned as SourcedValues with the bill page they came from; shares are derived in code and
carry their inputs' refs. A month read twice keeps its latest reading.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.sourced import SourcedValue, derive
from ..core.units import Unit
from ..db.models import Bill
from ..intake import bill_reading

os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "False")  # nothing about our bills leaves


# ---------------------------------------------------------------- which bills a person may see


def visible_bills(session: Session, actor: str | None, staff: bool) -> list[Bill]:
    """Analysts see every bill; anyone else the bills they uploaded."""
    q = select(Bill).order_by(Bill.bill_month, Bill.created_at)
    if not staff:
        q = q.where(Bill.uploaded_by.is_(None) if actor is None else Bill.uploaded_by == actor)
    return list(session.scalars(q))


# ---------------------------------------------------------------- search


class SearchHit(BaseModel):
    bill_id: str
    bill_month: date | None
    discom: str | None
    consumer: str | None
    account: str | None
    filename: str | None
    status: str
    score: float = Field(description="BM25 relevance, for ordering only")
    lines: list[str]
    reading_url: str


class SearchOut(BaseModel):
    query: str
    searched: int
    hits: list[SearchHit]


def _value(node: Any) -> str | None:
    if isinstance(node, dict) and "value" in node:
        v = node.get("value")
        return None if v is None else str(v)
    return None


def _walk(tree: Any, path: str) -> Any:
    node = tree
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _bill_dict(bill: Bill) -> dict[str, Any]:
    for b in (bill.billx_result or {}).get("bills", []):
        if int(b.get("index", 0)) == bill.bill_index:
            return dict(b)
    return {}


def bill_text(bill: Bill) -> list[str]:
    """The lines a bill is searched by: its identity, every labelled value, the slots and charges."""
    b = _bill_dict(bill)
    f = b.get("fields") or {}
    discom = (b.get("profile") or {}).get("id") or ""
    printed = (b.get("utility") or {}).get("name_as_printed") or ""
    lines = [
        f"file {bill.filename or ''}",
        f"status {bill.status}{' accepted' if bill.accepted else ''}",
        f"discom {discom} {printed}",
    ]
    for path in bill_reading.ORDER:
        v = _value(_walk(f, path))
        if v is not None:
            lines.append(f"{bill_reading.LABELS.get(path, path)}: {v}")
    for item in _walk(f, "energy.tod") or []:
        if not isinstance(item, dict):
            continue
        slot = item.get("slot")
        parts = [
            f"{k} {_value(item.get(k))}"
            for k in ("kwh", "kvah", "open_access", "net")
            if _value(item.get(k)) is not None
        ]
        lines.append(f"slot {slot}: " + ", ".join(parts))
    for e in b.get("elements") or []:
        if isinstance(e, dict) and _value(e.get("amount")) is not None:
            lines.append(f"charge {e.get('label')}: {_value(e.get('amount'))} ({e.get('code') or 'other'})")
    for c in b.get("checks") or []:
        if isinstance(c, dict) and c.get("status") == "fail":
            lines.append(f"check {c.get('id')} fails: {c.get('description') or ''}")
    for reason in b.get("review_reasons") or []:
        lines.append(f"to check: {reason}")
    return lines


_WORD = re.compile(r"[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*")


def search(bills: list[Bill], query: str, top_k: int = 10) -> SearchOut:
    """BM25 over the bills' lines (Haystack's in-memory store, rebuilt per call from what the
    person may see, so a hit never crosses clients)."""
    from haystack import Document
    from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
    from haystack.document_stores.in_memory import InMemoryDocumentStore

    texts = {b.id: bill_text(b) for b in bills}
    if not bills or not query.strip():
        return SearchOut(query=query, searched=len(bills), hits=[])
    store = InMemoryDocumentStore(bm25_algorithm="BM25Plus")
    store.write_documents(
        [Document(id=b.id, content="\n".join(texts[b.id]), meta={"bill_id": b.id}) for b in bills]
    )
    found = InMemoryBM25Retriever(store, top_k=top_k).run(query=query)["documents"]
    by_id = {b.id: b for b in bills}
    terms = {w.lower() for w in _WORD.findall(query) if len(w) > 1}
    hits = []
    for d in found:
        b = by_id.get(str(d.meta.get("bill_id")))
        if b is None or not d.score:
            continue
        lines = [ln for ln in texts[b.id] if terms & {w.lower() for w in _WORD.findall(ln)}][:6]
        if not lines:
            continue
        f = _bill_dict(b).get("fields") or {}
        hits.append(
            SearchHit(
                bill_id=b.id,
                bill_month=b.bill_month,
                discom=(_bill_dict(b).get("profile") or {}).get("id"),
                consumer=_value(_walk(f, "consumer.name")),
                account=_value(_walk(f, "consumer.account_number")),
                filename=b.filename,
                status=b.status,
                score=float(d.score),
                lines=lines,
                reading_url=f"/plan/intake/bill/{b.id}",
            )
        )
    return SearchOut(query=query, searched=len(bills), hits=hits)


# ---------------------------------------------------------------- analytics


class MonthSlot(BaseModel):
    slot: str
    consumption: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    open_access: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    billed: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )


class MonthRow(BaseModel):
    bill_id: str
    month: date
    verified: bool
    unit: str
    consumption: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    open_access: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    open_access_share: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result (derived)", "ref_kinds": ["bill"]}
    )
    billed: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    max_kva: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    contract_kva: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    power_factor: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    energy_charges: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    current_charges: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    net_payable: SourcedValue | None = Field(
        default=None, json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]}
    )
    slots: list[MonthSlot]


class AccountSeries(BaseModel):
    account: str | None
    consumer: str | None
    discom: str | None
    months: list[MonthRow]


class AnalyticsOut(BaseModel):
    accounts: list[AccountSeries]


@dataclass
class _Pick:
    bill: Bill
    reading: bill_reading.BillReading


def _sv(rv: bill_reading.ReadValue | None, unit: Unit) -> SourcedValue | None:
    if rv is None or rv.value is None or rv.source_ref is None:
        return None
    try:
        value = Decimal(str(rv.value).replace(",", ""))
    except ArithmeticError:
        return None
    return SourcedValue(value=value, unit=unit, source_refs=(rv.source_ref,), label=rv.label)


def analytics(session: Session, bills: list[Bill]) -> AnalyticsOut:
    """Each account's months, oldest first, the latest reading of a month kept."""
    latest: dict[tuple[str | None, date], _Pick] = {}
    for b in bills:
        if b.bill_month is None:
            continue
        try:
            r = bill_reading.build(session, b)
        except Exception:
            continue
        account = next((f.value for f in r.fields if f.path == "consumer.account_number"), None)
        key = (account, b.bill_month)
        if key not in latest or latest[key].bill.created_at <= b.created_at:
            latest[key] = _Pick(b, r)
    accounts: dict[str | None, AccountSeries] = {}
    for (account, month), pick in sorted(latest.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        r = pick.reading
        by = {f.path: f for f in r.fields}
        unit_name = r.tod[0].unit if r.tod else ("kWh" if by.get("energy.kwh") else "kVAh")
        eunit = Unit.KVAH if unit_name == "kVAh" else Unit.KWH
        slots = [
            MonthSlot(
                slot=t.slot,
                consumption=_sv(t.consumption, eunit),
                open_access=_sv(t.open_access, eunit),
                billed=_sv(t.net, eunit),
            )
            for t in r.tod
            if t.slot.strip().lower() != "total"
        ]
        consumption = _sv(by.get("energy.kvah") if eunit == Unit.KVAH else by.get("energy.kwh"), eunit)
        oa_parts = [s.open_access for s in slots if s.open_access is not None]
        open_access = (
            derive(sum((v.value for v in oa_parts), Decimal(0)), eunit, oa_parts, label="open access set off")
            if oa_parts
            else None
        )
        share = (
            derive(
                (open_access.value / consumption.value * 100).quantize(Decimal("0.01")),
                Unit.PERCENT,
                [open_access, consumption],
                label="open access share",
            )
            if open_access is not None and consumption is not None and consumption.value > 0
            else None
        )
        row = MonthRow(
            bill_id=pick.bill.id,
            month=month,
            verified=pick.bill.accepted,
            unit=unit_name,
            consumption=consumption,
            open_access=open_access,
            open_access_share=share,
            billed=_sv(by.get("energy.billed_units"), eunit),
            max_kva=_sv(by.get("demand.max_kva"), Unit.KVA),
            contract_kva=_sv(by.get("demand.contract_kva"), Unit.KVA),
            power_factor=_sv(by.get("energy.power_factor"), Unit.RATIO),
            energy_charges=_sv(by.get("charges.energy"), Unit.INR),
            current_charges=_sv(by.get("totals.current_charges"), Unit.INR),
            net_payable=_sv(by.get("totals.net_payable"), Unit.INR),
            slots=slots,
        )
        series = accounts.setdefault(
            account,
            AccountSeries(
                account=account,
                consumer=by["consumer.name"].value if "consumer.name" in by else None,
                discom=r.discom,
                months=[],
            ),
        )
        series.months.append(row)
    return AnalyticsOut(accounts=list(accounts.values()))
