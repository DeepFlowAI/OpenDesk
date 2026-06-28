"""backfill conversation queue summary fields

Revision ID: 9c0d1e2f3a4b
Revises: 8b9c0d1e2f3a
Create Date: 2026-06-27

Recomputes the materialized queue fields from queue_tasks + queue_assignment_events
using the same caliber as runtime materialization (app/libs/queue_metrics.py):

- a task waits from enqueued_at to its terminal time (assigned/canceled/timeout);
  tasks still waiting contribute 0 (no updated_at / now() fallback);
- a conversation's total wait is the sum over its online-chat conversation /
  open_agent_handoff tasks; NULL when 0 (no substantial queue);
- last assigned queue is the latest successful assignment event's queue.

Idempotent: rebuilds conversation_queue_summaries and overwrites the redundant
columns on every run.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "9c0d1e2f3a4b"
down_revision: Union[str, Sequence[str], None] = "8b9c0d1e2f3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SUCCESS_EVENT_TYPES = "('auto_assigned','pull_assigned','admin_assigned','returning_agent_assigned')"

# Per-task waiting seconds for relevant online-chat conversation tasks.
_TASK_WAIT_CTE = """
task_wait AS (
    SELECT
        qt.tenant_id,
        qt.task_ref_id::int AS conversation_id,
        qt.queue_type,
        qt.queue_id,
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
)
"""

# Latest successful assignment event per conversation -> last assigned queue.
_LAST_EVENT_CTE = f"""
last_ev AS (
    SELECT DISTINCT ON (conversation_id)
        conversation_id, queue_type, queue_id, queue_name_snapshot
    FROM (
        SELECT
            qt.task_ref_id::int AS conversation_id,
            e.queue_type, e.queue_id, e.queue_name_snapshot, e.created_at, e.id
        FROM queue_assignment_events e
        JOIN queue_tasks qt ON qt.id = e.task_id
        WHERE qt.channel = 'online_chat'
          AND qt.task_type IN ('conversation', 'open_agent_handoff')
          AND qt.task_ref_id ~ '^[0-9]+$'
          AND e.event_type IN {_SUCCESS_EVENT_TYPES}
    ) s
    ORDER BY conversation_id, created_at DESC, id DESC
)
"""

# Latest snapshot per (conversation, queue) from any event carrying one.
_SNAPSHOT_CTE = """
ev_snap AS (
    SELECT DISTINCT ON (conversation_id, queue_type, queue_id)
        conversation_id, queue_type, queue_id, queue_name_snapshot
    FROM (
        SELECT
            qt.task_ref_id::int AS conversation_id,
            e.queue_type, e.queue_id, e.queue_name_snapshot, e.created_at, e.id
        FROM queue_assignment_events e
        JOIN queue_tasks qt ON qt.id = e.task_id
        WHERE qt.channel = 'online_chat'
          AND qt.task_type IN ('conversation', 'open_agent_handoff')
          AND qt.task_ref_id ~ '^[0-9]+$'
          AND e.queue_name_snapshot IS NOT NULL
    ) s
    ORDER BY conversation_id, queue_type, queue_id, created_at DESC, id DESC
)
"""

_EMPLOYEE_NAME = "COALESCE(emp.display_name, emp.nickname, emp.name, emp.username)"


def upgrade() -> None:
    # 1) Conversation-level total queue duration (NULL when no substantial queue).
    op.execute(
        f"""
        WITH {_TASK_WAIT_CTE},
        conv_total AS (
            SELECT conversation_id, SUM(wait_seconds) AS total
            FROM task_wait
            GROUP BY conversation_id
            HAVING SUM(wait_seconds) > 0
        )
        UPDATE conversations c
        SET total_queue_duration_seconds = conv_total.total
        FROM conv_total
        WHERE c.id = conv_total.conversation_id
        """
    )

    # 2) Conversation-level last assigned queue.
    op.execute(
        f"""
        WITH {_LAST_EVENT_CTE}
        UPDATE conversations c
        SET last_assigned_queue_type = le.queue_type,
            last_assigned_queue_id   = le.queue_id,
            last_assigned_queue_name = COALESCE(
                le.queue_name_snapshot,
                CASE WHEN le.queue_type = 'employee_group' THEN eg.name END,
                CASE WHEN le.queue_type = 'employee' THEN {_EMPLOYEE_NAME} END
            )
        FROM last_ev le
        LEFT JOIN employee_groups eg ON le.queue_type = 'employee_group' AND eg.id = le.queue_id
        LEFT JOIN employees emp ON le.queue_type = 'employee' AND emp.id = le.queue_id
        WHERE c.id = le.conversation_id
        """
    )

    # 3) Per-queue summary rows (full rebuild).
    op.execute("DELETE FROM conversation_queue_summaries")
    op.execute(
        f"""
        WITH {_TASK_WAIT_CTE},
        {_LAST_EVENT_CTE},
        {_SNAPSHOT_CTE},
        agg AS (
            SELECT tenant_id, conversation_id, queue_type, queue_id, SUM(wait_seconds) AS wait_seconds
            FROM task_wait
            GROUP BY tenant_id, conversation_id, queue_type, queue_id
        )
        INSERT INTO conversation_queue_summaries (
            tenant_id, conversation_id, queue_type, queue_id, queue_name_snapshot,
            wait_duration_seconds, is_last_assigned, conversation_started_at,
            created_at, updated_at
        )
        SELECT
            agg.tenant_id,
            agg.conversation_id,
            agg.queue_type,
            agg.queue_id,
            COALESCE(
                snap.queue_name_snapshot,
                CASE WHEN agg.queue_type = 'employee_group' THEN eg.name END,
                CASE WHEN agg.queue_type = 'employee' THEN {_EMPLOYEE_NAME} END
            ),
            agg.wait_seconds,
            (le.conversation_id IS NOT NULL
                AND le.queue_type = agg.queue_type
                AND le.queue_id = agg.queue_id) AS is_last_assigned,
            c.started_at,
            now(),
            now()
        FROM agg
        JOIN conversations c ON c.id = agg.conversation_id
        LEFT JOIN ev_snap snap
            ON snap.conversation_id = agg.conversation_id
           AND snap.queue_type = agg.queue_type
           AND snap.queue_id = agg.queue_id
        LEFT JOIN last_ev le ON le.conversation_id = agg.conversation_id
        LEFT JOIN employee_groups eg ON agg.queue_type = 'employee_group' AND eg.id = agg.queue_id
        LEFT JOIN employees emp ON agg.queue_type = 'employee' AND emp.id = agg.queue_id
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM conversation_queue_summaries")
    op.execute(
        """
        UPDATE conversations
        SET total_queue_duration_seconds = NULL,
            last_assigned_queue_type = NULL,
            last_assigned_queue_id = NULL,
            last_assigned_queue_name = NULL
        """
    )
