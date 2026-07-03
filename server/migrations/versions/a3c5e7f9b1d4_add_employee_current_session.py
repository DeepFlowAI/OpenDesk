"""add employee current session

Revision ID: a3c5e7f9b1d4
Revises: c4d5e6f7a8b9
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c5e7f9b1d4"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("current_session_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_employees_tenant_current_session",
        "employees",
        ["tenant_id", "current_session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_employees_tenant_current_session", table_name="employees")
    op.drop_column("employees", "current_session_id")
