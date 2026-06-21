"""add conversation visitor environment

Revision ID: 3f4a5b6c7d8e
Revises: 2d3e4f5a6b7c
Create Date: 2026-06-18 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3f4a5b6c7d8e"
down_revision: Union[str, Sequence[str], None] = "2d3e4f5a6b7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("visitor_system", sa.String(length=64), nullable=True))
    op.add_column("conversations", sa.Column("visitor_browser", sa.String(length=128), nullable=True))
    op.add_column("conversations", sa.Column("visitor_ip", sa.String(length=45), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "visitor_ip")
    op.drop_column("conversations", "visitor_browser")
    op.drop_column("conversations", "visitor_system")
