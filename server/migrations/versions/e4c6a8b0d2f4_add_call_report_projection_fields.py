"""add call report projection fields

Revision ID: e4c6a8b0d2f4
Revises: e2b4d6f8a0c2
Create Date: 2026-08-31
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4c6a8b0d2f4"
down_revision: Union[str, Sequence[str], None] = "e2b4d6f8a0c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "call_records",
        sa.Column("human_service_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column("first_agent_wait_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column("first_agent_offer_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column("bot_handoff_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column("bot_handoff_succeeded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column("hangup_stage", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column("short_abandon_threshold_ms", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column(
            "call_short_abandon_threshold_seconds",
            sa.Integer(),
            server_default="5",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_system_settings_call_short_abandon_threshold",
        "system_settings",
        "call_short_abandon_threshold_seconds BETWEEN 1 AND 60",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_system_settings_call_short_abandon_threshold",
        "system_settings",
        type_="check",
    )
    op.drop_column("system_settings", "call_short_abandon_threshold_seconds")
    op.drop_column("call_records", "short_abandon_threshold_ms")
    op.drop_column("call_records", "hangup_stage")
    op.drop_column("call_records", "bot_handoff_succeeded_at")
    op.drop_column("call_records", "bot_handoff_requested_at")
    op.drop_column("call_records", "first_agent_offer_started_at")
    op.drop_column("call_records", "first_agent_wait_started_at")
    op.drop_column("call_records", "human_service_requested_at")
