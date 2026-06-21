"""add conversation user stat settings

Revision ID: 3b5d7f9a1c2e
Revises: 2a4b6c8d0e1f
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3b5d7f9a1c2e"
down_revision: Union[str, None] = "2a4b6c8d0e1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_user_stat_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("show_session_count", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("show_call_count", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("show_unresolved_ticket_count", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("show_total_ticket_count", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_conversation_user_stat_settings_tenant_id"),
    )
    op.create_index(
        "ix_conversation_user_stat_settings_tenant_id",
        "conversation_user_stat_settings",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_user_stat_settings_tenant_id", table_name="conversation_user_stat_settings")
    op.drop_table("conversation_user_stat_settings")
