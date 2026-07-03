"""widen conversations.ended_by to 32

Revision ID: d5e7f9a1b3c5
Revises: b4c6d8e0f2a4
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e7f9a1b3c5"
down_revision: Union[str, Sequence[str], None] = "b4c6d8e0f2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Newer end reasons like "handoff_leave_message" (22 chars) exceed the
    # original VARCHAR(16), so widen the column to hold them.
    op.alter_column(
        "conversations",
        "ended_by",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "conversations",
        "ended_by",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
