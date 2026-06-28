"""add conversation read status

Revision ID: 4c6e8f0a2b3d
Revises: 9b2c3d4e5f6a
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c6e8f0a2b3d"
down_revision: Union[str, Sequence[str], None] = "9b2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_read_status_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("agent_workspace_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("web_sdk_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_conversation_read_status_settings_tenant_id"),
    )
    op.create_index(
        "ix_conversation_read_status_settings_tenant_id",
        "conversation_read_status_settings",
        ["tenant_id"],
        unique=False,
    )
    op.add_column("messages", sa.Column("visitor_read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("agent_read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_messages_conversation_visitor_read",
        "messages",
        ["conversation_id", "visitor_read_at"],
        unique=False,
    )
    op.create_index(
        "ix_messages_conversation_agent_read",
        "messages",
        ["conversation_id", "agent_read_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_agent_read", table_name="messages")
    op.drop_index("ix_messages_conversation_visitor_read", table_name="messages")
    op.drop_column("messages", "agent_read_at")
    op.drop_column("messages", "visitor_read_at")
    op.drop_index("ix_conversation_read_status_settings_tenant_id", table_name="conversation_read_status_settings")
    op.drop_table("conversation_read_status_settings")
