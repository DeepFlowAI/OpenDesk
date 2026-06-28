"""add conversation queue lifecycle fields

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-27

Materializes the queue lifecycle on conversations so session records read them
directly instead of re-aggregating queue_tasks at query time. Caliber matches
the runtime materialization (app/libs/queue_metrics.py), derived only from
substantial tasks (waited > 0 seconds):

- queue_entered_at: earliest enqueued_at among substantial tasks;
- queue_assigned_at: latest assigned_at among substantial tasks (NULL if never
  assigned);
- queue_result: result of the latest substantial task — one of
  assigned / canceled / timeout (a substantial task always has a terminal time).

Idempotent: overwrites the columns on every run.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("queue_entered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("queue_assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("queue_result", sa.String(length=16), nullable=True))

    op.execute(
        """
        WITH subtask AS (
            SELECT
                qt.task_ref_id::int AS conversation_id,
                qt.id,
                qt.enqueued_at,
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
        substantial AS (
            SELECT * FROM subtask WHERE wait_seconds > 0
        ),
        agg AS (
            SELECT
                conversation_id,
                MIN(enqueued_at) AS queue_entered_at,
                MAX(assigned_at) AS queue_assigned_at
            FROM substantial
            GROUP BY conversation_id
        ),
        latest AS (
            SELECT DISTINCT ON (conversation_id)
                conversation_id,
                CASE
                    WHEN assigned_at IS NOT NULL THEN 'assigned'
                    WHEN canceled_at IS NOT NULL THEN 'canceled'
                    WHEN timeout_at IS NOT NULL THEN 'timeout'
                END AS queue_result
            FROM substantial
            ORDER BY conversation_id, COALESCE(terminal_at, enqueued_at) DESC, id DESC
        )
        UPDATE conversations c
        SET queue_entered_at = agg.queue_entered_at,
            queue_assigned_at = agg.queue_assigned_at,
            queue_result = latest.queue_result
        FROM agg
        JOIN latest ON latest.conversation_id = agg.conversation_id
        WHERE c.id = agg.conversation_id
        """
    )


def downgrade() -> None:
    op.drop_column("conversations", "queue_result")
    op.drop_column("conversations", "queue_assigned_at")
    op.drop_column("conversations", "queue_entered_at")
