"""add call wrapup seconds to system settings

Revision ID: c6e8f0a2b4d6
Revises: a4b5c6d7e8f9
Create Date: 2026-08-18

Additive: tenant-level after-call work duration in seconds (0 = skip wrap-up).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6e8f0a2b4d6"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("call_wrapup_seconds", sa.Integer(), server_default="30", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "call_wrapup_seconds")
