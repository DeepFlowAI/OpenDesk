"""rebackfill reception segment first response

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-27

Reception segments should not copy the conversation-level first response. The
conversation keeps its own first-human-response metric; the first segment only
stores a value when that segment's assigned agent replied within the segment
window. Later segments keep this field empty.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PUBLIC_CONTENT_TYPES = "'text', 'rich_text', 'image', 'file'"


def upgrade() -> None:
    op.execute("UPDATE conversation_reception_segments SET first_response_seconds = NULL")
    op.execute(
        f"""
        WITH first_agent_reply AS (
            SELECT
                seg.id AS segment_id,
                reply.id AS reply_id,
                reply.created_at AS reply_at
            FROM conversation_reception_segments seg
            JOIN LATERAL (
                SELECT msg.id, msg.created_at
                FROM messages msg
                WHERE msg.conversation_id = seg.conversation_id
                  AND msg.sender_type = 'agent'
                  AND msg.sender_id = seg.agent_id
                  AND msg.content_type IN ({PUBLIC_CONTENT_TYPES})
                  AND msg.created_at >= seg.started_at
                  AND (seg.ended_at IS NULL OR msg.created_at < seg.ended_at)
                  AND EXISTS (
                      SELECT 1
                      FROM messages visitor_msg
                      WHERE visitor_msg.conversation_id = seg.conversation_id
                        AND visitor_msg.sender_type = 'visitor'
                        AND visitor_msg.content_type IN ({PUBLIC_CONTENT_TYPES})
                        AND visitor_msg.created_at >= seg.started_at
                        AND (seg.ended_at IS NULL OR visitor_msg.created_at < seg.ended_at)
                        AND (
                            visitor_msg.created_at < msg.created_at
                            OR (visitor_msg.created_at = msg.created_at AND visitor_msg.id < msg.id)
                        )
                  )
                ORDER BY msg.created_at ASC, msg.id ASC
                LIMIT 1
            ) reply ON true
            WHERE seg.seq_no = 1
              AND seg.agent_id IS NOT NULL
        ),
        pending_visitor_message AS (
            SELECT
                far.segment_id,
                far.reply_at,
                visitor_msg.created_at AS pending_at
            FROM first_agent_reply far
            JOIN conversation_reception_segments seg ON seg.id = far.segment_id
            JOIN LATERAL (
                SELECT msg.created_at
                FROM messages msg
                WHERE msg.conversation_id = seg.conversation_id
                  AND msg.sender_type = 'visitor'
                  AND msg.content_type IN ({PUBLIC_CONTENT_TYPES})
                  AND msg.created_at >= seg.started_at
                  AND (seg.ended_at IS NULL OR msg.created_at < seg.ended_at)
                  AND (
                      msg.created_at < far.reply_at
                      OR (msg.created_at = far.reply_at AND msg.id < far.reply_id)
                  )
                ORDER BY msg.created_at DESC, msg.id DESC
                LIMIT 1
            ) visitor_msg ON true
        )
        UPDATE conversation_reception_segments seg
        SET first_response_seconds =
            GREATEST(0, EXTRACT(epoch FROM pvm.reply_at - pvm.pending_at))::int
        FROM pending_visitor_message pvm
        WHERE seg.id = pvm.segment_id
        """
    )


def downgrade() -> None:
    # Data-only backfill; previous per-row values are not retained.
    pass
