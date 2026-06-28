"""backfill first human response with greeting-aware caliber

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-27

Re-backfills the first public human-agent response duration for already-stored
closed conversations using the corrected caliber: the first agent reply is the
first public ``agent`` message *after* the conversation's first public
``visitor`` message, so a proactive agent greeting sent before any visitor
message no longer suppresses the metric. The reception-segment fact table copies
the conversation value into its first segment (``seq_no = 1``), so that column is
re-synced here as well.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PUBLIC_CONTENT_TYPES = "'text', 'rich_text', 'image', 'file'"


def upgrade() -> None:
    # Reset closed conversations so rows that no longer qualify become NULL.
    op.execute(
        """
        UPDATE conversations
        SET first_human_response_seconds = NULL
        WHERE status = 'closed'
          AND ended_at IS NOT NULL
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
                far.created_at AS reply_at,
                pvm.created_at AS pending_at
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
            GREATEST(0, EXTRACT(epoch FROM pvm.reply_at - pvm.pending_at))::int
        FROM pending_visitor_message pvm
        WHERE c.id = pvm.conversation_id
          AND c.status = 'closed'
          AND c.ended_at IS NOT NULL
        """
    )
    # Re-sync the first reception segment's copy of the conversation value.
    op.execute(
        """
        UPDATE conversation_reception_segments seg
        SET first_response_seconds = c.first_human_response_seconds
        FROM conversations c
        WHERE seg.conversation_id = c.id
          AND seg.seq_no = 1
        """
    )


def downgrade() -> None:
    # Data-only caliber backfill; previous per-row values are not retained.
    pass
