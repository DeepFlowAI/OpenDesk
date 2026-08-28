"""add auto outbound attempt_id for originate idempotency

Revision ID: c3d5e7f9a1b2
Revises: b2d4f6a8c0e2
Create Date: 2026-08-14

Additive: nullable attempt_id + partial unique index.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a8c0e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auto_outbound_call_records",
        sa.Column("attempt_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_auto_outbound_records_attempt_id",
        "auto_outbound_call_records",
        ["attempt_id"],
        unique=True,
        postgresql_where=sa.text("attempt_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_auto_outbound_records_attempt_id", table_name="auto_outbound_call_records")
    op.drop_column("auto_outbound_call_records", "attempt_id")
