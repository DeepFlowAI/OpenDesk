"""add tenant slug

Revision ID: 8b3f2c4d5e6a
Revises: 3d7f0256b3ad
Create Date: 2026-05-08 17:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b3f2c4d5e6a"
down_revision: Union[str, None] = "3d7f0256b3ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("slug", sa.String(length=128), nullable=True))
    op.create_index(
        "uq_tenants_slug_not_null",
        "tenants",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tenants_slug_not_null", table_name="tenants")
    op.drop_column("tenants", "slug")
