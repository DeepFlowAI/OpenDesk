"""add call events

Revision ID: f2a4c6e8b0d2
Revises: b9d0e1f2a3b4
Create Date: 2026-08-09 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2a4c6e8b0d2"
down_revision: Union[str, None] = "b9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=96), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.Integer(), nullable=False),
        sa.Column("root_call_id", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_category", sa.String(length=24), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence_no", sa.BigInteger(), nullable=False),
        sa.Column("operation_id", sa.String(length=96), nullable=True),
        sa.Column("call_leg_id", sa.String(length=96), nullable=True),
        sa.Column("parent_leg_id", sa.String(length=96), nullable=True),
        sa.Column("participant_role", sa.String(length=32), nullable=True),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("actor_id", sa.String(length=80), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=80), nullable=True),
        sa.Column("target_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("queue_type", sa.String(length=24), nullable=True),
        sa.Column("queue_id", sa.Integer(), nullable=True),
        sa.Column("queue_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("result", sa.String(length=24), nullable=True),
        sa.Column("reason_code", sa.String(length=48), nullable=True),
        sa.Column("reason_detail", sa.String(length=1000), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_call_events_event_id", "call_events", ["event_id"], unique=True)
    op.create_index(
        "uq_call_events_sequence", "call_events", ["call_record_id", "sequence_no"], unique=True
    )
    op.create_index(
        "uq_call_events_source_event",
        "call_events",
        ["source", "source_event_id"],
        unique=True,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )
    op.create_index(
        "ix_call_events_timeline",
        "call_events",
        ["call_record_id", "occurred_at", "sequence_no", "id"],
    )
    op.create_index("ix_call_events_root", "call_events", ["tenant_id", "root_call_id"])
    op.create_index("ix_call_events_operation", "call_events", ["call_record_id", "operation_id"])


def downgrade() -> None:
    op.drop_table("call_events")
