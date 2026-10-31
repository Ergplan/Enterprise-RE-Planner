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


class Jurisdiction(Base):
    """States, regulators, DISCOMs. DISCOM ids are billx profile ids (pvvnl, npcl, msedcl …)."""

    __tablename__ = "jurisdictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # state|regulator|discom|stu
    name: Mapped[str] = mapped_column(Text)
    state_code: Mapped[str | None] = mapped_column(String(8), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(32))


class RulebookVersion(Base):
    """One version of one family for one jurisdiction. Written only by rulebook.service; audited."""

    __tablename__ = "rulebook_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    family: Mapped[str] = mapped_column(String(32), index=True)
    jurisdiction_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|approved|superseded|rejected
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    title: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(
        String(32), default="manual"
    )  # manual|yaml|regreader_direct|tariff_oder
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    golden_status: Mapped[str] = mapped_column(String(16), default="not_run")  # not_run|green|red
    notes: Mapped[str | None] = mapped_column(Text)


class Rule(Base):
    """One rule row: scope (when it applies), body (the family's fields), source_ref (where it is
    written), field_refs (a citation per body field when it differs from the row's)."""

    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rulebook_version_id: Mapped[str] = mapped_column(String(36), index=True)
    family: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    body: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSONType)
    field_refs: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    review: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict
    )  # reader provenance, analyst decision


class RuleTest(Base):
    """A golden case: in this context, this rule field equals this value (cited)."""

    __tablename__ = "rule_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    jurisdiction_id: Mapped[str] = mapped_column(String(32), index=True)
    family: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(Text)
    given: Mapped[dict[str, Any]] = mapped_column(JSONType)
    expect: Mapped[dict[str, Any]] = mapped_column(JSONType)
    source_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONType)


class RuleTestRun(Base):
    __tablename__ = "rule_test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rulebook_version_id: Mapped[str] = mapped_column(String(36), index=True)
    test_id: Mapped[str] = mapped_column(String(36))
    passed: Mapped[bool] = mapped_column()
    actual: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Appended by trigger on every write to rules, rulebook_versions and rule_tests."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(64))
    row_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(8))
    actor: Mapped[str] = mapped_column(String(128))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
