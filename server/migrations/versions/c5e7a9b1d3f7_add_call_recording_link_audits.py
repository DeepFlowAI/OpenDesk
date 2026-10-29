"""add call recording link audits

Revision ID: c5e7a9b1d3f7
Revises: c5e7a9b1d3f6
Create Date: 2026-10-22

Additive: audit rows for recording download links issued via the Open API.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5e7a9b1d3f7"
down_revision: Union[str, Sequence[str], None] = "c5e7a9b1d3f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_recording_link_audits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("api_key_name", sa.String(length=100), nullable=False),
        sa.Column("call_public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recording_public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_call_recording_link_audit_tenant_created",
        "call_recording_link_audits",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_call_recording_link_audit_tenant_created",
        table_name="call_recording_link_audits",
    )
    op.drop_table("call_recording_link_audits")
