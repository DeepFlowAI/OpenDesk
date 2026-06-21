"""add visitor timeout close

Revision ID: 4a6c8e0f2b1d
Revises: 3b5d7f9a1c2e
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a6c8e0f2b1d"
down_revision: Union[str, None] = "3b5d7f9a1c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visitor_timeout_close_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("first_normal_minutes", sa.Integer(), server_default="110", nullable=False),
        sa.Column("close_normal_minutes", sa.Integer(), server_default="120", nullable=False),
        sa.Column("vip_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("first_vip_minutes", sa.Integer(), server_default="110", nullable=False),
        sa.Column("close_vip_minutes", sa.Integer(), server_default="120", nullable=False),
        sa.Column("first_reminder_content", sa.Text(), nullable=False),
        sa.Column("close_reminder_content", sa.Text(), nullable=False),
        sa.Column("notify_agent", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notify_visitor", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_visitor_timeout_close_settings_tenant_id"),
    )
    op.create_index(
        "ix_visitor_timeout_close_settings_tenant_id",
        "visitor_timeout_close_settings",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "visitor_timeout_close_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("anchor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchor_message_id", sa.Integer(), nullable=True),
        sa.Column("first_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["anchor_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_visitor_timeout_close_states_conversation_id"),
    )
    op.create_index(
        "ix_visitor_timeout_close_states_tenant_conversation",
        "visitor_timeout_close_states",
        ["tenant_id", "conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_visitor_timeout_close_states_tenant_next_check",
        "visitor_timeout_close_states",
        ["tenant_id", "next_check_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_visitor_timeout_close_states_tenant_next_check", table_name="visitor_timeout_close_states")
    op.drop_index("ix_visitor_timeout_close_states_tenant_conversation", table_name="visitor_timeout_close_states")
    op.drop_table("visitor_timeout_close_states")
    op.drop_index("ix_visitor_timeout_close_settings_tenant_id", table_name="visitor_timeout_close_settings")
    op.drop_table("visitor_timeout_close_settings")
