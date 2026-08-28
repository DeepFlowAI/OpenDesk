"""add schedule_rule_sets.targets_enabled

Revision ID: a8c9d0e1f2b3
Revises: e9f1a3b5c7d9
Create Date: 2026-08-08 23:30:00.000000

Additive column so coverage targets can be turned off (template-only generation).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c9d0e1f2b3"
down_revision: Union[str, None] = "e9f1a3b5c7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "schedule_rule_sets",
        sa.Column(
            "targets_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_rule_sets", "targets_enabled")
