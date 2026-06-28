"""add user blacklist field

Revision ID: 5b7d9f1a3c4e
Revises: 4a6c8e0f2b1d
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5b7d9f1a3c4e"
down_revision: Union[str, None] = "4a6c8e0f2b1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("blacklist", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "blacklist")
