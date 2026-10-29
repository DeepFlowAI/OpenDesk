"""add call agent facts

Revision ID: 5b11dd77ce5b
Revises: 4a10cc66bf4a
Create Date: 2026-09-01
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5b11dd77ce5b"
down_revision: Union[str, None] = "4a10cc66bf4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.add_column("call_records", sa.Column("initiator_agent_ref_id", sa.Integer(), nullable=True))
    op.add_column(
        "call_records", sa.Column("initiator_agent_name_snapshot", sa.String(length=255), nullable=True)
    )
    op.execute(
        "UPDATE call_records SET initiator_agent_ref_id = initiator_agent_id "
        "WHERE initiator_agent_ref_id IS NULL"
    )
    op.create_index(
        "ix_call_records_initiator_ref_started",
        "call_records",
        ["tenant_id", "initiator_agent_ref_id", "started_at"],
    )
    op.add_column("call_queue_offers", sa.Column("agent_ref_id", sa.Integer(), nullable=True))
    op.execute("UPDATE call_queue_offers SET agent_ref_id = agent_id WHERE agent_ref_id IS NULL")
    op.create_index(
        "ix_call_queue_offers_agent_ref_started",
        "call_queue_offers",
        ["tenant_id", "agent_ref_id", "started_at"],
    )
    op.create_table(
        "call_agent_reception_segments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=False),
        sa.Column("started_event_id", sa.String(length=96), nullable=False),
        sa.Column("ended_event_id", sa.String(length=96), nullable=True),
        sa.Column("segment_ordinal", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("agent_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_reason", sa.String(length=32), server_default="unknown", nullable=False),
        sa.Column("end_reason", sa.String(length=32), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("talk_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("hold_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("consult_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("held", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("result_reliable", sa.Boolean(), server_default="false", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("started_event_id", name="uq_call_agent_segments_started_event"),
        sa.UniqueConstraint(
            "call_record_id", "segment_ordinal", name="uq_call_agent_segments_call_ordinal"
        ),
    )
    op.create_index(
        "ix_call_agent_segments_report",
        "call_agent_reception_segments",
        ["tenant_id", "agent_id", "started_at"],
    )
    op.create_index(
        "ix_call_agent_segments_call",
        "call_agent_reception_segments",
        ["call_record_id", "started_at"],
    )
    op.create_table(
        "call_agent_operations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=False),
        sa.Column("operation_key", sa.String(length=128), nullable=False),
        sa.Column("operation_type", sa.String(length=24), nullable=False),
        sa.Column("actor_agent_id", sa.Integer(), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=80), nullable=True),
        sa.Column("target_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("started_event_id", sa.String(length=96), nullable=False),
        sa.Column("ended_event_id", sa.String(length=96), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=24), nullable=True),
        sa.Column("result_reliable", sa.Boolean(), server_default="false", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "call_record_id",
            "operation_key",
            "operation_type",
            "actor_agent_id",
            name="uq_call_agent_operations_identity",
        ),
    )
    op.create_index(
        "ix_call_agent_operations_report",
        "call_agent_operations",
        ["tenant_id", "actor_agent_id", "started_at"],
    )
    op.create_index(
        "ix_call_agent_operations_call",
        "call_agent_operations",
        ["call_record_id", "started_at"],
    )
    op.create_table(
        "call_agent_after_call_work",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=False),
        sa.Column("reception_segment_id", sa.BigInteger(), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("agent_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("end_reason", sa.String(length=32), nullable=True),
        sa.Column("result_reliable", sa.Boolean(), server_default="false", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reception_segment_id"], ["call_agent_reception_segments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_record_id", "agent_id", name="uq_call_agent_acw_call_agent"),
    )
    op.create_index(
        "ix_call_agent_acw_report",
        "call_agent_after_call_work",
        ["tenant_id", "agent_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_call_agent_acw_report", table_name="call_agent_after_call_work")
    op.drop_table("call_agent_after_call_work")
    op.drop_index("ix_call_agent_operations_call", table_name="call_agent_operations")
    op.drop_index("ix_call_agent_operations_report", table_name="call_agent_operations")
    op.drop_table("call_agent_operations")
    op.drop_index("ix_call_agent_segments_call", table_name="call_agent_reception_segments")
    op.drop_index("ix_call_agent_segments_report", table_name="call_agent_reception_segments")
    op.drop_table("call_agent_reception_segments")
    op.drop_index("ix_call_queue_offers_agent_ref_started", table_name="call_queue_offers")
    op.drop_column("call_queue_offers", "agent_ref_id")
    op.drop_index("ix_call_records_initiator_ref_started", table_name="call_records")
    op.drop_column("call_records", "initiator_agent_name_snapshot")
    op.drop_column("call_records", "initiator_agent_ref_id")
