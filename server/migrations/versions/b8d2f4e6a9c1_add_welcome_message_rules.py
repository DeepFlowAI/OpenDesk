"""add welcome message rules

Revision ID: b8d2f4e6a9c1
Revises: a7c9d8e1f2b3
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b8d2f4e6a9c1"
down_revision: Union[str, None] = "a7c9d8e1f2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "welcome_message_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_welcome_message_rules_tenant_id", "welcome_message_rules", ["tenant_id"], unique=False)
    op.create_index(
        "ix_welcome_message_rules_tenant_priority",
        "welcome_message_rules",
        ["tenant_id", "priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_welcome_message_rules_tenant_priority", table_name="welcome_message_rules")
    op.drop_index("ix_welcome_message_rules_tenant_id", table_name="welcome_message_rules")
    op.drop_table("welcome_message_rules")
