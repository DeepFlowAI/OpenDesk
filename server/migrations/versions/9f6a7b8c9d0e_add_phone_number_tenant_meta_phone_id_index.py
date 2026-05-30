"""add phone_number_id index on phone_number_tenant_meta

Revision ID: 9f6a7b8c9d0e
Revises: 8d4e5f6a7b8c
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "9f6a7b8c9d0e"
down_revision: Union[str, None] = "8d4e5f6a7b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_phone_number_tenant_meta_phone_number_id",
        "phone_number_tenant_meta",
        ["phone_number_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_phone_number_tenant_meta_phone_number_id",
        table_name="phone_number_tenant_meta",
    )
