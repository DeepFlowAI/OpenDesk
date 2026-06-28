"""add user assignee fields

Revision ID: 6a7b8c9d0e1f
Revises: 5b7d9f1a3c4e
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a7b8c9d0e1f"
down_revision: Union[str, None] = "5b7d9f1a3c4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "assignee_group_id",
            sa.Integer(),
            sa.ForeignKey("employee_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_users_agent", "users", ["agent_id"])
    op.create_index("ix_users_assignee_group", "users", ["assignee_group_id"])


def downgrade() -> None:
    op.drop_index("ix_users_assignee_group", table_name="users")
    op.drop_index("ix_users_agent", table_name="users")
    op.drop_column("users", "assignee_group_id")
    op.drop_column("users", "agent_id")
