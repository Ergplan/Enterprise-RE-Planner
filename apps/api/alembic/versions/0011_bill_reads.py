"""bill reads in the background

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-01 20:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bill_reads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("uploaded_by", sa.String(length=254), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("billx_job_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("bill_ids", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("replaces", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bill_reads_file_sha256", "bill_reads", ["file_sha256"])
    op.create_index("ix_bill_reads_uploaded_by", "bill_reads", ["uploaded_by"])
    op.create_index("ix_bill_reads_status", "bill_reads", ["status"])


def downgrade() -> None:
    op.drop_index("ix_bill_reads_status", table_name="bill_reads")
    op.drop_index("ix_bill_reads_uploaded_by", table_name="bill_reads")
    op.drop_index("ix_bill_reads_file_sha256", table_name="bill_reads")
    op.drop_table("bill_reads")
