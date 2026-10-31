"""SQLAlchemy models. One module so Alembic sees every table; each table names its writer in
docs/architecture.md."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.ids import new_id
from .base import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


class SourceDocument(Base):
    """A regulation, order or notification PDF. Written only by documents.service."""

    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(Text)
    regulator: Mapped[str | None] = mapped_column(String(32))
    jurisdiction: Mapped[str | None] = mapped_column(String(16))  # state code (UP, MH) or CERC
    document_kind: Mapped[str] = mapped_column(
        String(32), default="order"
    )  # order|regulation|notification|other
    utilities: Mapped[list[str]] = mapped_column(JSONType, default=list)
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_bytes: Mapped[int] = mapped_column(BigInteger)
    pages: Mapped[int] = mapped_column(Integer)
    order_date: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    url_public: Mapped[str | None] = mapped_column(Text)  # the regulator's own link
    notes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    page_hints: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict
    )  # e.g. {"schedule": [352, 400]}
    original_filename: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str] = mapped_column(String(128))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelCall(Base):
    """One row per external model call (rule 9). Written only by providers."""

    __tablename__ = "model_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_name: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(16))  # ok|failed|refused|unparseable
    error: Mapped[str | None] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
