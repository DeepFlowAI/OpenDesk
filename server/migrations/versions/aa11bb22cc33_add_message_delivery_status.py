"""add message delivery status

Revision ID: aa11bb22cc33
Revises: a2b3c4d5e6f8
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa11bb22cc33"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("visitor_online_at_send", sa.Boolean(), nullable=True))
    op.add_column("messages", sa.Column("visitor_delivered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "visitor_delivered_at")
    op.drop_column("messages", "visitor_online_at_send")
