"""add phone_number_tenant_meta for per-tenant tags

Revision ID: 8d4e5f6a7b8c
Revises: 7c3e4f5a6b7d
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "8d4e5f6a7b8c"
down_revision: Union[str, None] = "7c3e4f5a6b7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "phone_number_tenant_meta",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("phone_number_id", sa.String(32), nullable=False),
        sa.Column("tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["phone_number_id"], ["phone_numbers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "phone_number_id", name="uq_phone_number_tenant_meta"),
    )
    op.create_index(
        "ix_phone_number_tenant_meta_tenant_id",
        "phone_number_tenant_meta",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_phone_number_tenant_meta_tenant_id", table_name="phone_number_tenant_meta")
    op.drop_table("phone_number_tenant_meta")
