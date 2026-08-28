"""add embedded call record context

Revision ID: b2d4f6a8c0e2
Revises: a1c3e5f7b9d1
Create Date: 2026-08-13 19:10:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b2d4f6a8c0e2"
down_revision: Union[str, Sequence[str], None] = "a1c3e5f7b9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "call_records",
        sa.Column("custom_business_info", sa.Text(), nullable=True),
    )
    op.add_column(
        "call_records",
        sa.Column(
            "external_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("call_records", "external_context")
    op.drop_column("call_records", "custom_business_info")
