"""add sip_trunks and phone_numbers platform catalog tables

Revision ID: 7c3e4f5a6b7d
Revises: 6b2d3e4f5a6c
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "7c3e4f5a6b7d"
down_revision: Union[str, None] = "6b2d3e4f5a6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sip_trunks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("supplier_name", sa.String(128), nullable=False),
        sa.Column("trunk_name", sa.String(128), nullable=False),
        sa.Column("trunk_types", JSONB, nullable=False),
        sa.Column("remark", sa.String(256), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled"),
        sa.Column("peer_endpoints", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "uq_sip_trunks_trunk_name_lower",
        "sip_trunks",
        [sa.text("lower(trunk_name)")],
        unique=True,
    )

    op.create_table(
        "phone_numbers",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("phone_number", sa.String(64), nullable=False),
        sa.Column("call_types", JSONB, nullable=False),
        sa.Column("trunk_id", sa.String(32), nullable=True),
        sa.Column("tenant_id", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="available"),
        sa.Column("remark", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["trunk_id"], ["sip_trunks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="SET NULL"),
        sa.UniqueConstraint("phone_number", name="uq_phone_numbers_phone_number"),
    )
    op.create_index("ix_phone_numbers_trunk_id", "phone_numbers", ["trunk_id"])
    op.create_index("ix_phone_numbers_tenant_id", "phone_numbers", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_phone_numbers_tenant_id", table_name="phone_numbers")
    op.drop_index("ix_phone_numbers_trunk_id", table_name="phone_numbers")
    op.drop_table("phone_numbers")
    op.drop_index("uq_sip_trunks_trunk_name_lower", table_name="sip_trunks")
    op.drop_table("sip_trunks")
