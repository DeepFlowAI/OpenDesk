"""add quality plan scan checkpoint

Revision ID: a066cc22bd0a
Revises: 9f55bb11ac9f
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a066cc22bd0a"
down_revision: Union[str, None] = "9f55bb11ac9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quality_plans",
        sa.Column("last_candidate_scan_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quality_plans", "last_candidate_scan_at")
