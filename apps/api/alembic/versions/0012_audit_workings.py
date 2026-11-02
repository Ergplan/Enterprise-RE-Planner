"""the audit screen: workings, their lines, the audit chat, proposed rule changes

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-02 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

J = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _now() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "workings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("pages", J, nullable=False),
        sa.Column("uploaded_by", sa.String(length=254), nullable=False),
        _now(),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], name="workings_connection_fk"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workings_connection_id", "workings", ["connection_id"])
    op.create_index("ix_workings_sha256", "workings", ["sha256"])
    op.create_table(
        "working_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("working_id", sa.String(length=36), nullable=False),
        sa.Column("chain_key", sa.String(length=128), nullable=True),
        sa.Column("compare", sa.String(length=8), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(24, 6), nullable=False),
        sa.Column("scale", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("theirs", sa.Numeric(24, 6), nullable=True),
        sa.Column("ours", sa.Numeric(24, 6), nullable=True),
        sa.Column("ours_unit", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=254), nullable=False),
        _now(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('open','matches','differs','unmatched','ours_accepted','stated','proposed',"
            "'rule_changed','rejected')",
            name="working_lines_status",
        ),
        sa.ForeignKeyConstraint(["working_id"], ["workings.id"], name="working_lines_working_fk"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_working_lines_working_id", "working_lines", ["working_id"])
    op.create_index("ix_working_lines_chain_key", "working_lines", ["chain_key"])
    op.create_index("ix_working_lines_status", "working_lines", ["status"])
    op.create_table(
        "audit_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("data", J, nullable=False),
        sa.Column("actor", sa.String(length=254), nullable=False),
        _now(),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], name="audit_messages_connection_fk"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_messages_connection_id", "audit_messages", ["connection_id"])
    op.create_table(
        "rule_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("working_line_id", sa.String(length=36), nullable=True),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("family", sa.String(length=64), nullable=False),
        sa.Column("jurisdiction_id", sa.String(length=32), nullable=False),
        sa.Column("rule_label", sa.Text(), nullable=True),
        sa.Column("pointer", sa.Text(), nullable=False),
        sa.Column("current", sa.Numeric(24, 6), nullable=True),
        sa.Column("proposed", sa.Numeric(24, 6), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("proposed_by", sa.String(length=254), nullable=False),
        _now(),
        sa.Column("decided_by", sa.String(length=254), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("draft_version_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint("status in ('open','accepted','rejected')", name="rule_proposals_status"),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], name="rule_proposals_connection_fk"),
        sa.ForeignKeyConstraint(["working_line_id"], ["working_lines.id"], name="rule_proposals_line_fk"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rule_proposals_connection_id", "rule_proposals", ["connection_id"])
    op.create_index("ix_rule_proposals_rule_id", "rule_proposals", ["rule_id"])
    op.create_index("ix_rule_proposals_status", "rule_proposals", ["status"])


def downgrade() -> None:
    op.drop_table("rule_proposals")
    op.drop_table("audit_messages")
    op.drop_table("working_lines")
    op.drop_table("workings")
