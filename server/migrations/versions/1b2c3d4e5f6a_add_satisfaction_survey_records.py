"""add satisfaction survey records

Revision ID: 1b2c3d4e5f6a
Revises: 0a1b2c3d4e5f
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "1b2c3d4e5f6a"
down_revision: Union[str, None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "satisfaction_survey_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("visitor_id", sa.Integer(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("invitation_source", sa.String(length=24), server_default="agent", nullable=False),
        sa.Column("invited_by_id", sa.Integer(), nullable=True),
        sa.Column("invited_by_name", sa.String(length=128), nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="invited", nullable=False),
        sa.Column("survey_types", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("service_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("product_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["visitor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_satisfaction_records_conversation"),
    )
    op.create_index(
        "ix_satisfaction_records_tenant_conversation",
        "satisfaction_survey_records",
        ["tenant_id", "conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_satisfaction_records_tenant_status",
        "satisfaction_survey_records",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_satisfaction_records_tenant_version",
        "satisfaction_survey_records",
        ["tenant_id", "config_version"],
        unique=False,
    )

    op.create_table(
        "satisfaction_survey_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=128), nullable=True),
        sa.Column("summary", sa.String(length=200), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["record_id"], ["satisfaction_survey_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_satisfaction_events_conversation_time",
        "satisfaction_survey_events",
        ["conversation_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_satisfaction_events_record",
        "satisfaction_survey_events",
        ["record_id"],
        unique=False,
    )
    op.create_index(
        "ix_satisfaction_events_tenant_type",
        "satisfaction_survey_events",
        ["tenant_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_satisfaction_events_tenant_type", table_name="satisfaction_survey_events")
    op.drop_index("ix_satisfaction_events_record", table_name="satisfaction_survey_events")
    op.drop_index("ix_satisfaction_events_conversation_time", table_name="satisfaction_survey_events")
    op.drop_table("satisfaction_survey_events")
    op.drop_index("ix_satisfaction_records_tenant_version", table_name="satisfaction_survey_records")
    op.drop_index("ix_satisfaction_records_tenant_status", table_name="satisfaction_survey_records")
    op.drop_index("ix_satisfaction_records_tenant_conversation", table_name="satisfaction_survey_records")
    op.drop_table("satisfaction_survey_records")
