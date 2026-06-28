"""add bot phase visitor message count

Revision ID: f8a9b0c1d2e3
Revises: e5f6a7b8c9d0
Create Date: 2026-06-28

Adds an independent materialized count of visitor messages sent before the
human takeover (the bot phase). This is not a read-time derivation of
``bot_phase_message_count`` (which also includes bot replies): runtime
increments, end-of-conversation reconciliation, and this historical backfill
all count from the same message-caliber rules, so the report metric "bot-phase
visitor messages" never includes bot replies.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "bot_phase_visitor_message_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE conversations c SET
            bot_phase_visitor_message_count = m.bot_phase_visitor_count
        FROM (
            SELECT
                msg.conversation_id AS conversation_id,
                COUNT(*) FILTER (
                    WHERE msg.sender_type = 'visitor'
                      AND NOT (
                          cc.had_bot_session = false
                          OR (
                              cc.started_at IS NOT NULL
                              AND msg.created_at >= cc.started_at
                          )
                      )
                ) AS bot_phase_visitor_count
            FROM messages msg
            JOIN conversations cc ON cc.id = msg.conversation_id
            GROUP BY msg.conversation_id
        ) m
        WHERE c.id = m.conversation_id
        """
    )


def downgrade() -> None:
    op.drop_column("conversations", "bot_phase_visitor_message_count")
