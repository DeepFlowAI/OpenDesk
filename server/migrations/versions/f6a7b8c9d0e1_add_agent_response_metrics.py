"""add agent response metrics

Revision ID: f6a7b8c9d0e1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-27

Materializes the human-agent response stats on conversations. The source of
truth remains messages: over the public visitor/agent messages in chronological
order, each agent reply whose immediately preceding public message is a visitor
message is one response, measured from that last consecutive visitor message to
the reply. ``agent_response_count`` is the number of such responses (0 for an
ended session without any), ``agent_avg_response_seconds`` is the rounded
average whole-second duration (NULL when there is no response). Only ended
sessions are backfilled; in-progress sessions stay NULL.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PUBLIC_CONTENT_TYPES = "'text', 'rich_text', 'image', 'file'"


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("agent_response_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("agent_avg_response_seconds", sa.Integer(), nullable=True),
    )
    op.execute(
        f"""
        WITH public_messages AS (
            SELECT
                msg.conversation_id,
                msg.sender_type,
                msg.created_at,
                LAG(msg.sender_type) OVER w AS prev_sender_type,
                LAG(msg.created_at) OVER w AS prev_created_at
            FROM messages msg
            WHERE msg.sender_type IN ('visitor', 'agent')
              AND msg.content_type IN ({PUBLIC_CONTENT_TYPES})
            WINDOW w AS (
                PARTITION BY msg.conversation_id
                ORDER BY msg.created_at ASC, msg.id ASC
            )
        ),
        responses AS (
            SELECT
                conversation_id,
                GREATEST(0, EXTRACT(epoch FROM created_at - prev_created_at))::int
                    AS response_seconds
            FROM public_messages
            WHERE sender_type = 'agent'
              AND prev_sender_type = 'visitor'
        ),
        agg AS (
            SELECT
                conversation_id,
                COUNT(*) AS response_count,
                ROUND(AVG(response_seconds))::int AS avg_seconds
            FROM responses
            GROUP BY conversation_id
        )
        UPDATE conversations c
        SET agent_response_count = COALESCE(agg.response_count, 0),
            agent_avg_response_seconds = agg.avg_seconds
        FROM (
            SELECT id FROM conversations
            WHERE status = 'closed' AND ended_at IS NOT NULL
        ) closed
        LEFT JOIN agg ON agg.conversation_id = closed.id
        WHERE c.id = closed.id
        """
    )


def downgrade() -> None:
    op.drop_column("conversations", "agent_avg_response_seconds")
    op.drop_column("conversations", "agent_response_count")
