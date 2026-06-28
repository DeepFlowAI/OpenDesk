"""add message recall fields

Revision ID: 5d6e7f8a9b0c
Revises: 4c6e8f0a2b3d
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5d6e7f8a9b0c"
down_revision: Union[str, Sequence[str], None] = "4c6e8f0a2b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("is_recalled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("messages", sa.Column("recalled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("recalled_by_type", sa.String(length=16), nullable=True))
    op.add_column("messages", sa.Column("recalled_by_id", sa.Integer(), nullable=True))
    op.add_column("messages", sa.Column("recalled_by_name", sa.String(length=255), nullable=True))
    op.create_index("ix_messages_recalled", "messages", ["is_recalled"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_recalled", table_name="messages")
    op.drop_column("messages", "recalled_by_name")
    op.drop_column("messages", "recalled_by_id")
    op.drop_column("messages", "recalled_by_type")
    op.drop_column("messages", "recalled_at")
    op.drop_column("messages", "is_recalled")
