"""add call satisfaction projection

Revision ID: c6e8a0b2d4f6
Revises: b5d7f9a1c3e5
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6e8a0b2d4f6"
down_revision: Union[str, None] = "b5d7f9a1c3e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "call_records",
        sa.Column("human_service_ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "call_records", sa.Column("satisfaction_result", sa.String(length=24), nullable=True)
    )
    op.add_column(
        "call_records",
        sa.Column("satisfaction_trigger_source", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column("satisfaction_primary_option_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column("satisfaction_primary_option_label", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "call_records", sa.Column("satisfaction_answer_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "call_records", sa.Column("satisfaction_duration_ms", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "call_records",
        sa.Column("satisfaction_projected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_cr_tenant_satisfaction_result_started",
        "call_records",
        ["tenant_id", "satisfaction_result", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_cr_tenant_satisfaction_source_started",
        "call_records",
        ["tenant_id", "satisfaction_trigger_source", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cr_tenant_satisfaction_source_started", table_name="call_records")
    op.drop_index("ix_cr_tenant_satisfaction_result_started", table_name="call_records")
    op.drop_column("call_records", "satisfaction_projected_at")
    op.drop_column("call_records", "satisfaction_duration_ms")
    op.drop_column("call_records", "satisfaction_answer_count")
    op.drop_column("call_records", "satisfaction_primary_option_label")
    op.drop_column("call_records", "satisfaction_primary_option_id")
    op.drop_column("call_records", "satisfaction_trigger_source")
    op.drop_column("call_records", "satisfaction_result")
    op.drop_column("call_records", "human_service_ended_at")
