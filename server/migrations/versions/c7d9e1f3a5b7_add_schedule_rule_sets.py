"""add schedule rule sets

Revision ID: c7d9e1f3a5b7
Revises: b5c7d9e1f3a5
Create Date: 2026-08-08 18:30:00.000000

Scheduling Center phase 2: rule sets (schedule_rule_sets) holding coverage
targets, work-hour constraints and rotation templates as JSONB. Additive only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7d9e1f3a5b7"
down_revision: Union[str, None] = "b5c7d9e1f3a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_rule_sets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("default_group_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("targets", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("constraints", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("rotation_templates", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_schedule_rule_sets_tenant_name"),
    )
    op.create_index("ix_schedule_rule_sets_tenant_id", "schedule_rule_sets", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_schedule_rule_sets_tenant_id", table_name="schedule_rule_sets")
    op.drop_table("schedule_rule_sets")
