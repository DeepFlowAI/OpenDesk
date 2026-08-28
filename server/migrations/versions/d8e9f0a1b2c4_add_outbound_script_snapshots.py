"""Add outbound script template and task snapshot columns.

Revision ID: d8e9f0a1b2c4
Revises: c7a8b9d0e1f2
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8e9f0a1b2c4"
down_revision: Union[str, Sequence[str], None] = "c7a8b9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outbound_task_templates",
        sa.Column("script", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "outbound_tasks",
        sa.Column("script_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outbound_tasks", "script_snapshot")
    op.drop_column("outbound_task_templates", "script")
