"""add first human response seconds

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-27

Materializes the first public human-agent response duration on conversations.
The source of truth remains messages:
- first agent reply: first public ``agent`` message after the conversation's
  first public ``visitor`` message (a proactive greeting before any visitor
  message is skipped);
- pending visitor message: latest public ``visitor`` message before that reply;
- result: whole seconds between the two timestamps, NULL when there is no public
  visitor message or no agent reply after one.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PUBLIC_CONTENT_TYPES = "'text', 'rich_text', 'image', 'file'"


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("first_human_response_seconds", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE conversations
        SET first_human_response_seconds = NULL
        """
    )
    op.execute(
        f"""
        WITH first_visitor_message AS (
            SELECT DISTINCT ON (msg.conversation_id)
                msg.conversation_id,
                msg.id,
                msg.created_at
            FROM messages msg
            WHERE msg.sender_type = 'visitor'
              AND msg.content_type IN ({PUBLIC_CONTENT_TYPES})
            ORDER BY msg.conversation_id, msg.created_at ASC, msg.id ASC
        ),
        first_agent_reply AS (
            SELECT
                fvm.conversation_id,
                ar.id,
                ar.created_at
            FROM first_visitor_message fvm
            JOIN LATERAL (
                SELECT msg.id, msg.created_at
                FROM messages msg
                WHERE msg.conversation_id = fvm.conversation_id
                  AND msg.sender_type = 'agent'
                  AND msg.content_type IN ({PUBLIC_CONTENT_TYPES})
                  AND (
                      msg.created_at > fvm.created_at
                      OR (msg.created_at = fvm.created_at AND msg.id > fvm.id)
                  )
                ORDER BY msg.created_at ASC, msg.id ASC
                LIMIT 1
            ) ar ON true
        ),
        pending_visitor_message AS (
            SELECT
                far.conversation_id,
                pvm.created_at
            FROM first_agent_reply far
            JOIN LATERAL (
                SELECT msg.created_at
                FROM messages msg
                WHERE msg.conversation_id = far.conversation_id
                  AND msg.sender_type = 'visitor'
                  AND msg.content_type IN ({PUBLIC_CONTENT_TYPES})
                  AND (
                      msg.created_at < far.created_at
                      OR (msg.created_at = far.created_at AND msg.id < far.id)
                  )
                ORDER BY msg.created_at DESC, msg.id DESC
                LIMIT 1
            ) pvm ON true
        )
        UPDATE conversations c
        SET first_human_response_seconds =
            GREATEST(0, EXTRACT(epoch FROM far.created_at - pvm.created_at))::int
        FROM first_agent_reply far
        JOIN pending_visitor_message pvm ON pvm.conversation_id = far.conversation_id
        WHERE c.id = far.conversation_id
          AND c.status = 'closed'
          AND c.ended_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("conversations", "first_human_response_seconds")
