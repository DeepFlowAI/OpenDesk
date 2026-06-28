"""backfill conversation message counts

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-27

Recomputes the materialized message counts from the messages table using the
same caliber as the runtime increment and the end-of-conversation reconcile
(app/libs/conversation_metrics.py + ConversationRepository):

- visitor_message_count / agent_message_count: count by sender_type;
- phase split classifies each visitor message by the human-takeover anchor
  (started_at on bot conversations); agent always counts as the human phase,
  bot as the bot phase, system as neither. A conversation that never had a bot
  (had_bot_session = false) is entirely human phase.

Idempotent: zeroes the columns first, then overwrites from messages.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE conversations SET
            visitor_message_count = 0,
            agent_message_count = 0,
            bot_phase_message_count = 0,
            human_phase_message_count = 0
        """
    )
    op.execute(
        """
        UPDATE conversations c SET
            visitor_message_count = m.visitor_count,
            agent_message_count = m.agent_count,
            bot_phase_message_count = m.bot_phase_count,
            human_phase_message_count = m.human_phase_count
        FROM (
            SELECT
                msg.conversation_id AS conversation_id,
                COUNT(*) FILTER (WHERE msg.sender_type = 'visitor') AS visitor_count,
                COUNT(*) FILTER (WHERE msg.sender_type = 'agent') AS agent_count,
                COUNT(*) FILTER (
                    WHERE msg.sender_type = 'bot'
                       OR (
                           msg.sender_type = 'visitor'
                           AND NOT (
                               cc.had_bot_session = false
                               OR (
                                   cc.started_at IS NOT NULL
                                   AND msg.created_at >= cc.started_at
                               )
                           )
                       )
                ) AS bot_phase_count,
                COUNT(*) FILTER (
                    WHERE msg.sender_type = 'agent'
                       OR (
                           msg.sender_type = 'visitor'
                           AND (
                               cc.had_bot_session = false
                               OR (
                                   cc.started_at IS NOT NULL
                                   AND msg.created_at >= cc.started_at
                               )
                           )
                       )
                ) AS human_phase_count
            FROM messages msg
            JOIN conversations cc ON cc.id = msg.conversation_id
            GROUP BY msg.conversation_id
        ) m
        WHERE c.id = m.conversation_id
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE conversations SET
            visitor_message_count = 0,
            agent_message_count = 0,
            bot_phase_message_count = 0,
            human_phase_message_count = 0
        """
    )
