"""SourcedValue and SourceRef: invariant 1.

Every number a client sees is a SourcedValue: a Decimal, its unit, and at least one SourceRef.
A regulation or order ref must name the stored document, the page and a verbatim quote, and it
resolves to `/documents/{document_id}#page={page}`. Values the client typed or ergPLAN assumed
carry `client_stated` or `assumption` refs and are shown as editable chips, never as sourced facts.
A derived value carries the refs of every input (`derive`).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from .money import to_decimal
from .units import Unit


class RefKind(StrEnum):
    REGULATION = "regulation"
    ORDER = "order"
    CLIENT_STATED = "client_stated"
    ASSUMPTION = "assumption"
    MEASURED = "measured"
    DERIVED = "derived"
    BILL = "bill"  # read by billx from the client's own bill (invariant 7); links to the stored bill page


DOCUMENT_KINDS = {RefKind.REGULATION, RefKind.ORDER}


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RefKind
    document_id: str | None = None
    page: int | None = Field(default=None, ge=1)
    printed_page: str | None = None
    quote: str | None = Field(default=None, max_length=400)
    effective_from: date | None = None
    effective_to: date | None = None
    note: str | None = Field(default=None, max_length=500)
    rule_id: str | None = None  # the rule row this value came from, when it came from one
    bill_id: str | None = None  # kind bill: bills.id
    field_path: str | None = None  # kind bill: the billx contract path (demand.max_kva)

    @model_validator(mode="after")
    def _document_refs_are_complete(self) -> SourceRef:
        if self.kind in DOCUMENT_KINDS and not (self.document_id and self.page and self.quote):
            raise ValueError("a regulation or order ref needs document_id, page and quote")
        if self.kind == RefKind.BILL and not (self.bill_id and self.field_path):
            raise ValueError("a bill ref needs bill_id and field_path")
        return self

    @property
    def url(self) -> str | None:
        """The link that opens the stored PDF at the cited page."""
        if self.document_id and self.page:
            return f"/documents/{self.document_id}#page={self.page}"
        if self.kind == RefKind.BILL and self.bill_id:
            return f"/bills/{self.bill_id}/file" + (f"#page={self.page}" if self.page else "")
        return None

    def to_json(self) -> dict[str, Any]:
        d = self.model_dump(mode="json", exclude_none=True)
        if self.url:
            d["url"] = self.url
        return d


class SourcedValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: Decimal
    unit: Unit
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    label: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _decimal_only(cls, v: object) -> Decimal:
        return to_decimal(v)

    @field_serializer("value")
    def _value_as_string(self, v: Decimal) -> str:
        return format(v, "f")

    @property
    def is_sourced(self) -> bool:
        """True when every ref points at a document or the client's bill (not stated, not assumed)."""
        return all(
            r.kind in DOCUMENT_KINDS or r.kind in (RefKind.DERIVED, RefKind.BILL) for r in self.source_refs
        )


def derive(
    value: Decimal, unit: Unit, inputs: Iterable[SourcedValue], label: str | None = None
) -> SourcedValue:
    """A value computed from other sourced values carries all of their refs, de-duplicated in order."""
    refs: list[SourceRef] = []
    for sv in inputs:
        for r in sv.source_refs:
            if r not in refs:
                refs.append(r)
    if not refs:
        raise ValueError("a derived value needs at least one sourced input")
    return SourcedValue(value=value, unit=unit, source_refs=tuple(refs), label=label)


def stated(value: object, unit: Unit, note: str | None = None, label: str | None = None) -> SourcedValue:
    return SourcedValue(
        value=to_decimal(value),
        unit=unit,
        label=label,
        source_refs=(SourceRef(kind=RefKind.CLIENT_STATED, note=note),),
    )


def assumed(value: object, unit: Unit, note: str, label: str | None = None) -> SourcedValue:
    return SourcedValue(
        value=to_decimal(value),
        unit=unit,
        label=label,
        source_refs=(SourceRef(kind=RefKind.ASSUMPTION, note=note),),
    )
