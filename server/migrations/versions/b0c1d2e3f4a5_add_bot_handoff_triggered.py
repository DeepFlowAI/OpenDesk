"""add bot_handoff_triggered to conversations

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-06-28

Materializes whether a bot-to-human handoff was ever triggered (any non-null
``open_agent_handoff_state``), kept distinct from ``bot_handoff_succeeded``
(success only). It is the denominator for the handoff success rate, so reports
can count "triggered" vs "succeeded" without re-deriving the state predicate.
Runtime writes and this backfill share the caliber in
app/libs/conversation_metrics.py.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "bot_handoff_triggered",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE conversations
        SET bot_handoff_triggered = (open_agent_handoff_state IS NOT NULL)
        """
    )


def downgrade() -> None:
    op.drop_column("conversations", "bot_handoff_triggered")
