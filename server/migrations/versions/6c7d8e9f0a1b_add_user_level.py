"""add user level

Revision ID: 6c7d8e9f0a1b
Revises: 3f4a5b6c7d8e
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c7d8e9f0a1b"
down_revision: Union[str, Sequence[str], None] = "3f4a5b6c7d8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("level", sa.String(length=16), server_default="normal", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "level")
