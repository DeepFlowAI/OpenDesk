"""add conversation announcement rules

Revision ID: 7b8c9d0e1f2a
Revises: 6a7b8c9d0e1f
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7b8c9d0e1f2a"
down_revision: Union[str, None] = "6a7b8c9d0e1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_announcement_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("time_range_type", sa.String(length=16), server_default=sa.text("'permanent'"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("auto_popup", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("background_color", sa.String(length=16), server_default=sa.text("'yellow'"), nullable=False),
        sa.Column("summary_html", sa.Text(), nullable=False),
        sa.Column("detail_html", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_announcement_rules_tenant_enabled",
        "conversation_announcement_rules",
        ["tenant_id", "enabled"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_announcement_rules_tenant_id",
        "conversation_announcement_rules",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_announcement_rules_tenant_priority",
        "conversation_announcement_rules",
        ["tenant_id", "priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_announcement_rules_tenant_priority", table_name="conversation_announcement_rules")
    op.drop_index("ix_conversation_announcement_rules_tenant_id", table_name="conversation_announcement_rules")
    op.drop_index("ix_conversation_announcement_rules_tenant_enabled", table_name="conversation_announcement_rules")
    op.drop_table("conversation_announcement_rules")
