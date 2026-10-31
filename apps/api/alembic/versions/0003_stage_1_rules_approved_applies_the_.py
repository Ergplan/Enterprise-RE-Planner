"""stage 1: rules_approved applies the evaluation date

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 00:42:45.785246

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        (Path(__file__).resolve().parents[2] / "ergplan/db/sql/0003_rules_approved_on_date.sql").read_text()
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "CREATE OR REPLACE VIEW rules_approved AS SELECT r.id, r.rulebook_version_id, r.family, r.position, r.label, "
        "r.scope, r.body, r.source_ref, r.field_refs, v.jurisdiction_id, v.version, v.effective_from, v.effective_to "
        "FROM rules r JOIN rulebook_versions v ON v.id = r.rulebook_version_id WHERE v.status = 'approved'"
    )
