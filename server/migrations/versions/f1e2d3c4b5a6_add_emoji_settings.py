"""add emoji settings

Revision ID: f1e2d3c4b5a6
Revises: 6d7e8f9a0b1c
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f1e2d3c4b5a6"
down_revision: Union[str, None] = "6d7e8f9a0b1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emoji_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("agent_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("user_emojis", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("agent_emojis", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_emoji_settings_tenant_id"),
    )
    op.create_index("ix_emoji_settings_tenant_id", "emoji_settings", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_emoji_settings_tenant_id", table_name="emoji_settings")
    op.drop_table("emoji_settings")
