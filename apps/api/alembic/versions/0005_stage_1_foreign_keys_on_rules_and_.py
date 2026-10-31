"""stage 1: foreign keys on rules and golden runs

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01 00:45:06.850881

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key("rules_version_fk", "rules", "rulebook_versions", ["rulebook_version_id"], ["id"])
    op.create_foreign_key(
        "rule_test_runs_version_fk", "rule_test_runs", "rulebook_versions", ["rulebook_version_id"], ["id"]
    )
    op.create_foreign_key(
        "rule_test_runs_test_fk", "rule_test_runs", "rule_tests", ["test_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("rule_test_runs_test_fk", "rule_test_runs")
    op.drop_constraint("rule_test_runs_version_fk", "rule_test_runs")
    op.drop_constraint("rules_version_fk", "rules")
