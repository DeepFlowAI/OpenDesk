"""add event delivery retention index

Revision ID: d0f2a4c6e8b0
Revises: c9e1f3a5b7d9
Create Date: 2026-08-25

Additive partial index for bounded terminal delivery cleanup.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d0f2a4c6e8b0"
down_revision: Union[str, Sequence[str], None] = "c9e1f3a5b7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_event_deliveries_completed_retention",
        "event_deliveries",
        ["completed_at", "id"],
        unique=False,
        postgresql_where=sa.text(
            "status IN ('succeeded', 'failed') AND completed_at IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_deliveries_completed_retention",
        table_name="event_deliveries",
    )
