"""add conversation basic report fields

Revision ID: a0b1c2d3e4f5
Revises: 9c0d1e2f3a4b
Create Date: 2026-06-27

Materializes three read-only report fields on conversations:
- had_bot_session: served by an OpenAgent bot (OR over the OpenAgent ids);
- bot_handoff_succeeded: open_agent_handoff_state = 'success';
- duration_seconds: ended_at - started_at for ended sessions (NULL while live).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "9c0d1e2f3a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("had_bot_session", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("bot_handoff_succeeded", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "duration_seconds")
    op.drop_column("conversations", "bot_handoff_succeeded")
    op.drop_column("conversations", "had_bot_session")
