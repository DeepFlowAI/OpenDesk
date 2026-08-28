"""add personal auto outbound opening script

Revision ID: a4b5c6d7e8f9
Revises: e4f6a8b0c2d4
Create Date: 2026-08-18

Additive: nullable opening-script columns on recordings and sessions.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "e4f6a8b0c2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personal_outbound_recordings",
        sa.Column("script_text", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "personal_auto_outbound_sessions",
        sa.Column("opening_script_text", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "personal_auto_outbound_calls",
        sa.Column("last_utterance", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("personal_auto_outbound_calls", "last_utterance")
    op.drop_column("personal_auto_outbound_sessions", "opening_script_text")
    op.drop_column("personal_outbound_recordings", "script_text")
