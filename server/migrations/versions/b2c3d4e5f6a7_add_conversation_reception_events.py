"""add conversation reception events

Revision ID: b2c3d4e5f6a7
Revises: a2b3c4d5e6f7
Create Date: 2026-06-27

Adds the ``conversation_reception_events`` table — an append-only, agent-id
accurate fact source of responsibility changes within a conversation (first
human takeover, bot-to-human handoff, transfer, admin reassign, end). The
post-end reception-segment generation reads these instead of system-message
text, which only carries agent names.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_reception_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("from_agent_id", sa.Integer(), nullable=True),
        sa.Column("to_agent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["group_id"], ["employee_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["from_agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reception_events_conversation",
        "conversation_reception_events",
        ["conversation_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_reception_events_tenant_agent",
        "conversation_reception_events",
        ["tenant_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reception_events_tenant_agent", table_name="conversation_reception_events")
    op.drop_index("ix_reception_events_conversation", table_name="conversation_reception_events")
    op.drop_table("conversation_reception_events")
