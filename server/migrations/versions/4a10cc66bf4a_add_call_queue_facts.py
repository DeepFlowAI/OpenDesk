"""add call queue facts

Revision ID: 4a10cc66bf4a
Revises: e4c6a8b0d2f4
Create Date: 2026-09-01 10:14:32.437790

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a10cc66bf4a"
down_revision: Union[str, None] = "e4c6a8b0d2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_queue_visits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=False),
        sa.Column("entered_event_id", sa.String(length=96), nullable=False),
        sa.Column("exited_event_id", sa.String(length=96), nullable=True),
        sa.Column("visit_ordinal", sa.Integer(), nullable=False),
        sa.Column("queue_type", sa.String(length=24), nullable=False),
        sa.Column("queue_id", sa.Integer(), nullable=False),
        sa.Column("queue_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("entry_kind", sa.String(length=24), server_default="unknown", nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wait_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("result", sa.String(length=24), nullable=True),
        sa.Column("result_reliable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_short_abandon", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "call_record_id", "visit_ordinal", name="uq_call_queue_visits_call_ordinal"
        ),
        sa.UniqueConstraint("entered_event_id", name="uq_call_queue_visits_entered_event"),
    )
    op.create_index(
        "ix_call_queue_visits_call",
        "call_queue_visits",
        ["call_record_id", "entered_at"],
    )
    op.create_index(
        "ix_call_queue_visits_report",
        "call_queue_visits",
        ["tenant_id", "queue_type", "queue_id", "entered_at"],
    )
    op.create_table(
        "call_queue_offers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=False),
        sa.Column("queue_visit_id", sa.BigInteger(), nullable=False),
        sa.Column("started_event_id", sa.String(length=96), nullable=False),
        sa.Column("ended_event_id", sa.String(length=96), nullable=True),
        sa.Column("operation_id", sa.String(length=96), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("agent_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("result", sa.String(length=24), nullable=True),
        sa.Column("result_reliable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["queue_visit_id"], ["call_queue_visits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("started_event_id", name="uq_call_queue_offers_started_event"),
    )
    op.create_index(
        "ix_call_queue_offers_tenant_started",
        "call_queue_offers",
        ["tenant_id", "started_at"],
    )
    op.create_index(
        "ix_call_queue_offers_visit",
        "call_queue_offers",
        ["queue_visit_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_call_queue_offers_visit", table_name="call_queue_offers")
    op.drop_index("ix_call_queue_offers_tenant_started", table_name="call_queue_offers")
    op.drop_table("call_queue_offers")
    op.drop_index("ix_call_queue_visits_report", table_name="call_queue_visits")
    op.drop_index("ix_call_queue_visits_call", table_name="call_queue_visits")
    op.drop_table("call_queue_visits")
