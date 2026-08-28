"""fix schedule_published_snapshots.published_by FK to employees

Revision ID: e9f1a3b5c7d9
Revises: d8e0f2a4b6c8
Create Date: 2026-08-08 20:00:00.000000

# migration-safety: contract-approved

Auth principal.user_id is an employees.id. The initial snapshot migration
incorrectly referenced users.id, so publish failed with ForeignKeyViolationError.
This table is brand-new and never held a successful published_by pointing at users.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9f1a3b5c7d9"
down_revision: Union[str, None] = "d8e0f2a4b6c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "schedule_published_snapshots_published_by_fkey",
        "schedule_published_snapshots",
        type_="foreignkey",
    )
    op.execute(
        sa.text(
            "UPDATE schedule_published_snapshots SET published_by = NULL "
            "WHERE published_by IS NOT NULL "
            "AND published_by NOT IN (SELECT id FROM employees)"
        )
    )
    op.create_foreign_key(
        "schedule_published_snapshots_published_by_fkey",
        "schedule_published_snapshots",
        "employees",
        ["published_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "schedule_published_snapshots_published_by_fkey",
        "schedule_published_snapshots",
        type_="foreignkey",
    )
    op.execute(
        sa.text(
            "UPDATE schedule_published_snapshots SET published_by = NULL "
            "WHERE published_by IS NOT NULL "
            "AND published_by NOT IN (SELECT id FROM users)"
        )
    )
    op.create_foreign_key(
        "schedule_published_snapshots_published_by_fkey",
        "schedule_published_snapshots",
        "users",
        ["published_by"],
        ["id"],
        ondelete="SET NULL",
    )
