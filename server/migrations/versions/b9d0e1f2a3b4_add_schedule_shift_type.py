"""add schedule shift type

Revision ID: b9d0e1f2a3b4
Revises: a8c9d0e1f2b3
Create Date: 2026-08-09 12:00:00.000000

Additive classification for work shifts and all-day leave types. Existing
rows remain work shifts through the server default.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9d0e1f2a3b4"
down_revision: Union[str, None] = "a8c9d0e1f2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "schedule_shifts",
        sa.Column(
            "shift_type",
            sa.String(length=16),
            server_default=sa.text("'work'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_schedule_shifts_shift_type",
        "schedule_shifts",
        "shift_type IN ('work', 'leave')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_schedule_shifts_shift_type",
        "schedule_shifts",
        type_="check",
    )
    op.drop_column("schedule_shifts", "shift_type")
