"""backfill conversation basic report fields

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-06-27

Recomputes the materialized basic report fields from the existing OpenAgent
fields and session timestamps using the same caliber as runtime write hooks
(app/libs/conversation_metrics.py):

- had_bot_session: any of the three OpenAgent identity fields is set;
- bot_handoff_succeeded: open_agent_handoff_state = 'success';
- duration_seconds: ended_at - started_at (clamped >= 0) for ended sessions,
  NULL while in progress.

Idempotent: overwrites the columns on every run.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bot markers from the OpenAgent identity / handoff fields.
    op.execute(
        """
        UPDATE conversations SET
            had_bot_session = (
                open_agent_agent_id IS NOT NULL
                OR open_agent_conversation_id IS NOT NULL
                OR open_agent_conversation_external_id IS NOT NULL
            ),
            bot_handoff_succeeded = COALESCE(open_agent_handoff_state = 'success', false)
        """
    )

    # Duration for ended sessions only.
    op.execute(
        """
        UPDATE conversations SET
            duration_seconds = GREATEST(0, EXTRACT(epoch FROM ended_at - started_at))::int
        WHERE ended_at IS NOT NULL AND started_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE conversations SET
            had_bot_session = false,
            bot_handoff_succeeded = false,
            duration_seconds = NULL
        """
    )
