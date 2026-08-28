"""add auto resume on target append

Revision ID: e1a3c5e7f9b1
Revises: d0f2a4c6e8b0
Create Date: 2026-08-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1a3c5e7f9b1"
down_revision: Union[str, Sequence[str], None] = "d0f2a4c6e8b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auto_outbound_tasks",
        sa.Column(
            "auto_resume_on_target_append",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("auto_outbound_tasks", "auto_resume_on_target_append")
