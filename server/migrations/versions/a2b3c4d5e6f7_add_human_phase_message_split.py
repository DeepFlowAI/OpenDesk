"""add human phase message split

Revision ID: a2b3c4d5e6f7
Revises: f6a7b8c9d0e1
Create Date: 2026-06-27

Adds independent materialized counts for human-phase visitor and agent
messages. These columns are not read-time derivations: runtime increments,
end-of-conversation reconciliation, and this historical backfill all count from
the same message-caliber rules.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "human_phase_visitor_message_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "human_phase_agent_message_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE conversations c SET
            human_phase_visitor_message_count = m.human_phase_visitor_count,
            human_phase_agent_message_count = m.human_phase_agent_count
        FROM (
            SELECT
                msg.conversation_id AS conversation_id,
                COUNT(*) FILTER (
                    WHERE msg.sender_type = 'visitor'
                      AND (
                          cc.had_bot_session = false
                          OR (
                              cc.started_at IS NOT NULL
                              AND msg.created_at >= cc.started_at
                          )
                      )
                ) AS human_phase_visitor_count,
                COUNT(*) FILTER (
                    WHERE msg.sender_type = 'agent'
                ) AS human_phase_agent_count
            FROM messages msg
            JOIN conversations cc ON cc.id = msg.conversation_id
            GROUP BY msg.conversation_id
        ) m
        WHERE c.id = m.conversation_id
        """
    )


def downgrade() -> None:
    op.drop_column("conversations", "human_phase_agent_message_count")
    op.drop_column("conversations", "human_phase_visitor_message_count")
