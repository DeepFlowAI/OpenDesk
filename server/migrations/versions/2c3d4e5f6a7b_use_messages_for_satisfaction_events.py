"""use messages for satisfaction events

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f6a
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2c3d4e5f6a7b"
down_revision: Union[str, None] = "1b2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )
    op.alter_column(
        "messages",
        "content_type",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )

    op.drop_index("ix_satisfaction_events_tenant_type", table_name="satisfaction_survey_events")
    op.drop_index("ix_satisfaction_events_record", table_name="satisfaction_survey_events")
    op.drop_index("ix_satisfaction_events_conversation_time", table_name="satisfaction_survey_events")
    op.drop_table("satisfaction_survey_events")


def downgrade() -> None:
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

    op.alter_column(
        "messages",
        "content_type",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.drop_column("messages", "metadata")
