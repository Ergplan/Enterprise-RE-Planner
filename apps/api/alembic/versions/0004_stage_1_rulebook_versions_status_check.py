"""stage 1: rulebook_versions status check

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01 00:43:49.486050

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "rulebook_versions_status",
        "rulebook_versions",
        "status in ('draft','approved','superseded','rejected')",
    )
    op.create_check_constraint(
        "rulebook_versions_golden", "rulebook_versions", "golden_status in ('not_run','green','red')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("rulebook_versions_golden", "rulebook_versions")
    op.drop_constraint("rulebook_versions_status", "rulebook_versions")
