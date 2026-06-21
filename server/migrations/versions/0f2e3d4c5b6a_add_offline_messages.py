"""add offline messages

Revision ID: 0f2e3d4c5b6a
Revises: f1e2d3c4b5a6
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0f2e3d4c5b6a"
down_revision: Union[str, None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "offline_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("visitor_id", sa.Integer(), nullable=True),
        sa.Column("visitor_external_id", sa.String(length=128), nullable=False),
        sa.Column("visitor_name", sa.String(length=128), nullable=True),
        sa.Column("target_group_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("handled_by_id", sa.Integer(), nullable=True),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("last_message_preview", sa.String(length=200), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["handled_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_group_id"], ["employee_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["visitor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_offline_messages_tenant_status", "offline_messages", ["tenant_id", "status"], unique=False)
    op.create_index(
        "ix_offline_messages_tenant_last_message",
        "offline_messages",
        ["tenant_id", "last_message_at"],
        unique=False,
    )
    op.create_index(
        "ix_offline_messages_tenant_channel_visitor",
        "offline_messages",
        ["tenant_id", "channel_id", "visitor_external_id"],
        unique=False,
    )
    op.create_index(
        "ix_offline_messages_target_group",
        "offline_messages",
        ["tenant_id", "target_group_id"],
        unique=False,
    )
    op.create_index(
        "uq_offline_messages_pending_visitor",
        "offline_messages",
        ["tenant_id", "channel_id", "visitor_external_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "offline_message_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("offline_message_id", sa.Integer(), nullable=False),
        sa.Column("sender_type", sa.String(length=16), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=32), server_default="text", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["offline_message_id"], ["offline_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_offline_message_entries_message_created",
        "offline_message_entries",
        ["offline_message_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_offline_message_entries_tenant_message",
        "offline_message_entries",
        ["tenant_id", "offline_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_offline_message_entries_tenant_message", table_name="offline_message_entries")
    op.drop_index("ix_offline_message_entries_message_created", table_name="offline_message_entries")
    op.drop_table("offline_message_entries")
    op.drop_index("uq_offline_messages_pending_visitor", table_name="offline_messages")
    op.drop_index("ix_offline_messages_target_group", table_name="offline_messages")
    op.drop_index("ix_offline_messages_tenant_channel_visitor", table_name="offline_messages")
    op.drop_index("ix_offline_messages_tenant_last_message", table_name="offline_messages")
    op.drop_index("ix_offline_messages_tenant_status", table_name="offline_messages")
    op.drop_table("offline_messages")
