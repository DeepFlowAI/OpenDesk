"""add conversation queue summary fields and table

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-06-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "8b9c0d1e2f3a"
down_revision: Union[str, Sequence[str], None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("last_assigned_queue_type", sa.String(length=32), nullable=True))
    op.add_column("conversations", sa.Column("last_assigned_queue_id", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("last_assigned_queue_name", sa.String(length=128), nullable=True))
    op.add_column("conversations", sa.Column("total_queue_duration_seconds", sa.Integer(), nullable=True))

    op.create_table(
        "conversation_queue_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("queue_type", sa.String(length=32), nullable=False),
        sa.Column("queue_id", sa.Integer(), nullable=False),
        sa.Column("queue_name_snapshot", sa.String(length=128), nullable=True),
        sa.Column("wait_duration_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_last_assigned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("conversation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "queue_type", "queue_id", name="uq_conv_queue_summary"),
    )
    op.create_index(
        "ix_conv_queue_summary_queue",
        "conversation_queue_summaries",
        ["tenant_id", "queue_type", "queue_id"],
    )
    op.create_index(
        "ix_conv_queue_summary_started",
        "conversation_queue_summaries",
        ["tenant_id", "conversation_started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conv_queue_summary_started", table_name="conversation_queue_summaries")
    op.drop_index("ix_conv_queue_summary_queue", table_name="conversation_queue_summaries")
    op.drop_table("conversation_queue_summaries")
    op.drop_column("conversations", "total_queue_duration_seconds")
    op.drop_column("conversations", "last_assigned_queue_name")
    op.drop_column("conversations", "last_assigned_queue_id")
    op.drop_column("conversations", "last_assigned_queue_type")
