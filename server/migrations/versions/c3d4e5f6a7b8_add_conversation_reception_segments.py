"""add conversation reception segments

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-27

Adds the ``conversation_reception_segments`` per-conversation fact table and the
reception-segment aggregate columns on ``conversations``. Segments are generated
in bulk after a conversation ends; the aggregate columns are redundant, read-only
copies so session-record lists read them without aggregating the fact table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_reception_segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("agent_name_snapshot", sa.String(length=128), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("group_name_snapshot", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("entry_reason", sa.String(length=24), nullable=False),
        sa.Column("end_reason", sa.String(length=24), nullable=True),
        sa.Column("from_agent_id", sa.Integer(), nullable=True),
        sa.Column("to_agent_id", sa.Integer(), nullable=True),
        sa.Column("visitor_message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("agent_message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("first_response_seconds", sa.Integer(), nullable=True),
        sa.Column("avg_response_seconds", sa.Integer(), nullable=True),
        sa.Column("conversation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["group_id"], ["employee_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["from_agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "seq_no", name="uq_reception_segment_seq"),
    )
    op.create_index(
        "ix_reception_segment_tenant_agent",
        "conversation_reception_segments",
        ["tenant_id", "agent_id", "conversation_started_at"],
    )
    op.create_index(
        "ix_reception_segment_conversation",
        "conversation_reception_segments",
        ["conversation_id"],
    )

    op.add_column(
        "conversations",
        sa.Column("reception_segment_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("reception_transfer_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("reception_final_agent_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "reception_participants",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("reception_generation_status", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "reception_generation_status")
    op.drop_column("conversations", "reception_participants")
    op.drop_column("conversations", "reception_final_agent_id")
    op.drop_column("conversations", "reception_transfer_count")
    op.drop_column("conversations", "reception_segment_count")
    op.drop_index("ix_reception_segment_conversation", table_name="conversation_reception_segments")
    op.drop_index("ix_reception_segment_tenant_agent", table_name="conversation_reception_segments")
    op.drop_table("conversation_reception_segments")
