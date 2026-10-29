"""add auto outbound record call_variables

Revision ID: 85c1e2150f10
Revises: d2e3f4a5b6c7
Create Date: 2026-10-19

Additive: nullable JSONB snapshot of variables preset to the voice bot.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "85c1e2150f10"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auto_outbound_call_records",
        sa.Column("call_variables", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auto_outbound_call_records", "call_variables")
