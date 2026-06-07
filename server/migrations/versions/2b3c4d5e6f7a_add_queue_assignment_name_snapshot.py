"""add queue assignment name snapshot

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-05-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2b3c4d5e6f7a"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "queue_assignment_events",
        sa.Column("queue_name_snapshot", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("queue_assignment_events", "queue_name_snapshot")
