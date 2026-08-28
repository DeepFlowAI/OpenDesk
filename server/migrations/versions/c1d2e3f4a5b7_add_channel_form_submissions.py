"""add channel form submissions

Revision ID: c1d2e3f4a5b7
Revises: a1c2d3e4f5a6
Create Date: 2026-08-04 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c1d2e3f4a5b7"
down_revision: Union[str, None] = "a1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_form_submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("config_version_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("visitor_user_id", sa.Integer(), nullable=False),
        sa.Column("visitor_external_id", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="outside_service_hours", nullable=False),
        sa.Column("queue_type", sa.String(length=32), nullable=True),
        sa.Column("queue_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("field_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["config_version_id"], ["channel_form_config_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["visitor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", name="uq_channel_form_submissions_ticket"),
        sa.UniqueConstraint("tenant_id", "channel_id", "visitor_external_id", "idempotency_key", name="uq_channel_form_submissions_idempotency"),
    )
    op.create_index("ix_channel_form_submissions_tenant_ticket", "channel_form_submissions", ["tenant_id", "ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_channel_form_submissions_tenant_ticket", table_name="channel_form_submissions")
    op.drop_table("channel_form_submissions")
