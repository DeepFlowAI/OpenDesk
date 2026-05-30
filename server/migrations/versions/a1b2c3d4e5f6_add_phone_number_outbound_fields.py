"""add concurrency, called_number_prefix, outbound_time_slots to phone_numbers

Revision ID: a1b2c3d4e5f6
Revises: 9f6a7b8c9d0e
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9f6a7b8c9d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("phone_numbers", sa.Column("concurrency", sa.Integer(), nullable=True))
    op.add_column(
        "phone_numbers",
        sa.Column("called_number_prefix", sa.String(32), nullable=True),
    )
    op.add_column(
        "phone_numbers",
        sa.Column(
            "outbound_time_slots",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("phone_numbers", "outbound_time_slots")
    op.drop_column("phone_numbers", "called_number_prefix")
    op.drop_column("phone_numbers", "concurrency")
