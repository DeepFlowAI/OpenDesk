"""add per-queue queue_result to conversation_queue_summaries

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-28

Adds a per-queue terminal result (assigned / canceled / timeout) to each
conversation/queue summary row. ``is_last_assigned`` only marks the
conversation's final queue, so it cannot say whether a visitor who queued in a
given queue was eventually assigned there or dropped (canceled/timeout). The
result is derived from each queue's latest substantial task (wait > 0), using
the same caliber as runtime materialization (app/libs/queue_metrics.py). Queues
with no substantial wait carry NULL.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_queue_summaries",
        sa.Column("queue_result", sa.String(length=16), nullable=True),
    )
    op.execute(
        """
        WITH task_wait AS (
            SELECT
                qt.task_ref_id::int AS conversation_id,
                qt.queue_type,
                qt.queue_id,
                qt.id AS task_id,
                qt.assigned_at,
                qt.canceled_at,
                qt.timeout_at,
                COALESCE(qt.assigned_at, qt.canceled_at, qt.timeout_at) AS terminal_at,
                GREATEST(
                    0,
                    COALESCE(
                        EXTRACT(epoch FROM COALESCE(qt.assigned_at, qt.canceled_at, qt.timeout_at) - qt.enqueued_at),
                        0
                    )
                )::int AS wait_seconds
            FROM queue_tasks qt
            WHERE qt.channel = 'online_chat'
              AND qt.task_type IN ('conversation', 'open_agent_handoff')
              AND qt.task_ref_id ~ '^[0-9]+$'
        ),
        latest_substantial AS (
            SELECT DISTINCT ON (conversation_id, queue_type, queue_id)
                conversation_id,
                queue_type,
                queue_id,
                CASE
                    WHEN assigned_at IS NOT NULL THEN 'assigned'
                    WHEN canceled_at IS NOT NULL THEN 'canceled'
                    WHEN timeout_at IS NOT NULL THEN 'timeout'
                END AS queue_result
            FROM task_wait
            WHERE wait_seconds > 0
            ORDER BY conversation_id, queue_type, queue_id, terminal_at DESC, task_id DESC
        )
        UPDATE conversation_queue_summaries s
        SET queue_result = ls.queue_result
        FROM latest_substantial ls
        WHERE s.conversation_id = ls.conversation_id
          AND s.queue_type = ls.queue_type
          AND s.queue_id = ls.queue_id
        """
    )


def downgrade() -> None:
    op.drop_column("conversation_queue_summaries", "queue_result")
