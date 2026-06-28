"""add conversation message count fields

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-27

Materializes four read-only message-count columns on conversations so reports
read them instead of COUNT/JOIN-ing the messages table:
- visitor_message_count: messages where sender_type = 'visitor';
- agent_message_count: messages where sender_type = 'agent';
- bot_phase_message_count: visitor + bot messages before human takeover;
- human_phase_message_count: visitor + agent messages after human takeover.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("visitor_message_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("agent_message_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("bot_phase_message_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("human_phase_message_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("conversations", "human_phase_message_count")
    op.drop_column("conversations", "bot_phase_message_count")
    op.drop_column("conversations", "agent_message_count")
    op.drop_column("conversations", "visitor_message_count")
