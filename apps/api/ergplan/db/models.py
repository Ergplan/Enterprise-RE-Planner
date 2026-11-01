"""SQLAlchemy models. One module so Alembic sees every table; each table names its writer in
docs/architecture.md."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
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
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','approved','superseded','rejected')", name="rulebook_versions_status"
        ),
        CheckConstraint("golden_status in ('not_run','green','red')", name="rulebook_versions_golden"),
    )

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
    rulebook_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rulebook_versions.id", name="rules_version_fk"), index=True
    )
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
    rulebook_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rulebook_versions.id", name="rule_test_runs_version_fk"), index=True
    )
    test_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rule_tests.id", name="rule_test_runs_test_fk", ondelete="CASCADE")
    )
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


# ---------------------------------------------------------------- Stage 2: intake


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(Text)
    gstin: Mapped[str | None] = mapped_column(String(15))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id", name="sites_client_fk"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(8))
    address: Mapped[str | None] = mapped_column(Text)
    industry_shape: Mapped[str] = mapped_column(String(32), default="two_shift")
    shift_hours: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    weekly_off: Mapped[list[int]] = mapped_column(JSONType, default=list)  # 0=Mon … 6=Sun
    land_acres: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    roof_sqm: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict
    )  # field → bill|client_stated|assumption
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", name="connections_site_fk"), index=True
    )
    discom_id: Mapped[str] = mapped_column(String(32))
    consumer_number: Mapped[str | None] = mapped_column(String(64))
    tariff_category: Mapped[str | None] = mapped_column(String(64))
    voltage_kv: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    contract_demand_kva: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    connection_kind: Mapped[str] = mapped_column(String(8), default="ht")  # ht|eht|lt
    rate_block: Mapped[str | None] = mapped_column(String(32))  # urban|rural where the schedule splits
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Bill(Base):
    """A bill as billx read it (invariant 7: billx is the only bill reader)."""

    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    connection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("connections.id", name="bills_connection_fk")
    )
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str | None] = mapped_column(Text)
    billx_job_id: Mapped[str | None] = mapped_column(String(64))
    bill_index: Mapped[int] = mapped_column(Integer, default=0)  # a file can hold several bills
    bill_month: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(32)
    )  # billx status: passed|confirmed|needs_review|unreadable|…
    accepted: Mapped[bool] = mapped_column(default=False)
    accepted_by: Mapped[str | None] = mapped_column(String(64))  # engine|human|bill_confirmations
    billx_result: Mapped[dict[str, Any]] = mapped_column(JSONType)
    uploaded_by: Mapped[str | None] = mapped_column(String(254), index=True)  # who dropped the file (Stage 8)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillRead(Base):
    """One uploaded file being read by billx in the background (the worker submits it and polls);
    when billx finishes, its bills become `bills` rows and their ids are listed here."""

    __tablename__ = "bill_reads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    connection_id: Mapped[str | None] = mapped_column(String(36))
    uploaded_by: Mapped[str | None] = mapped_column(String(254), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="queued", index=True
    )  # queued|reading|done|failed
    billx_job_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    bill_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    # a reading again of a file (after billx improved): the bills it replaces once it is done
    replaces: Mapped[list[str]] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BillConfirmation(Base):
    __tablename__ = "bill_confirmations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bills.id", name="bill_confirmations_bill_fk"), index=True
    )
    path: Mapped[str] = mapped_column(String(128))
    value: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[str] = mapped_column(String(128))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", name="assets_site_fk"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # rooftop_pv|captive_thermal|waste_heat|bess|dg
    params: Mapped[dict[str, Any]] = mapped_column(JSONType)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class LoadProfile(Base):
    """A year of 15-minute demand (kW) for a connection, with how it was made (invariant 8)."""

    __tablename__ = "load_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("connections.id", name="load_profiles_connection_fk"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    provenance: Mapped[str] = mapped_column(String(16))  # measured|synthesised|stated
    resolution_min: Mapped[int] = mapped_column(Integer, default=15)
    year_start: Mapped[date] = mapped_column(Date)
    blocks: Mapped[int] = mapped_column(Integer)
    series_kw: Mapped[bytes] = mapped_column(LargeBinary)  # zlib-compressed text of decimals, one per block
    method: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("provenance in ('measured','synthesised','stated')", name="load_profiles_provenance"),
    )


class PriceVintage(Base):
    """One uploaded IEX price file (invariant 8: every result names the vintage it priced with)."""

    __tablename__ = "price_vintages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    segment: Mapped[str] = mapped_column(String(8))  # dam|rtm|gdam|gtam|tam|hpdam
    filename: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    rows: Mapped[int] = mapped_column(Integer)
    duplicates_dropped: Mapped[int] = mapped_column(Integer, default=0)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    source_note: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str] = mapped_column(String(128))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    superseded_by: Mapped[str | None] = mapped_column(String(36))


class PricePoint(Base):
    __tablename__ = "price_series"

    vintage_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("price_vintages.id", name="price_series_vintage_fk", ondelete="CASCADE"),
        primary_key=True,
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    block: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1..96, block 1 = 00:00-00:15
    segment: Mapped[str] = mapped_column(String(8), index=True)
    mcp_inr_per_mwh: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    mcv_mw: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


# ---------------------------------------------------------------- Stage 6: scenarios and runs


class Scenario(Base):
    """What to size for a connection: candidate sources, price assumptions, sensitivity ranges."""

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", name="scenarios_site_fk"), index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("connections.id", name="scenarios_connection_fk"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Run(Base):
    """One solve of a scenario, with every pin needed to replay it (invariant 5). Audited."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", name="runs_scenario_fk"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="queued")
    resolution_min: Mapped[int] = mapped_column(Integer, default=15)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONType)  # the scenario spec as run
    pins: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    solver: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    replay_of: Mapped[str | None] = mapped_column(String(36), ForeignKey("runs.id", name="runs_replay_fk"))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status in ('queued','running','done','failed','failed_resettle')", name="runs_status"
        ),
    )


class RunResult(Base):
    """A run's outputs: the client-facing summary (SourcedValues), the re-settlement check and the
    settled dispatch (zlib-compressed JSON)."""

    __tablename__ = "run_results"

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", name="run_results_run_fk", ondelete="CASCADE"), primary_key=True
    )
    summary: Mapped[dict[str, Any]] = mapped_column(JSONType)
    resettle: Mapped[dict[str, Any]] = mapped_column(JSONType)
    dispatch: Mapped[bytes] = mapped_column(LargeBinary)
    digest: Mapped[str] = mapped_column(String(64))  # sha256 of the canonical summary, for replay


# ---------------------------------------------------------------- Stage 7: live plan


class ShareLink(Base):
    """An unguessable token that opens a site's live plan (/p/{token}) without logging in (rule 12)."""

    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("connections.id", name="share_links_connection_fk"), index=True
    )
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Explanation(Base):
    """A short English explanation drafted by the model from SourcedValues only, cached by input."""

    __tablename__ = "explanations"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of prompt + input
    prompt: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    model_call_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- Stage 8: login


class User(Base):
    """A person who signs in, by email and password or by email link. Role analyst (jouleWise) or
    client. Only a scrypt hash of the password is stored (platform/passwords.py)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("role in ('analyst','client')", name="users_role"),)


class LoginToken(Base):
    """A one-time sign-in link (only its SHA-256 is stored)."""

    __tablename__ = "login_tokens"

    token_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    """A signed-in browser (only the SHA-256 of the cookie value is stored)."""

    __tablename__ = "auth_sessions"

    token_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(
        String(254), ForeignKey("users.email", name="auth_sessions_user_fk"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
