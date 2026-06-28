"""add conversation pins

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_pins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "agent_id",
            "conversation_id",
            name="uq_conversation_pins_agent_conversation",
        ),
    )
    op.create_index(
        "ix_conversation_pins_agent_pinned_at",
        "conversation_pins",
        ["tenant_id", "agent_id", "pinned_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_pins_conversation",
        "conversation_pins",
        ["tenant_id", "conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_pins_conversation", table_name="conversation_pins")
    op.drop_index("ix_conversation_pins_agent_pinned_at", table_name="conversation_pins")
    op.drop_table("conversation_pins")
