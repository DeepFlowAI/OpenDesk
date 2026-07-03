"""add verify_files domain verification catalog table

Revision ID: e1f2a3b4c5d6
Revises: d2e4f6a8b0c2
Create Date: 2026-06-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d2e4f6a8b0c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "verify_files",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("filename", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("remark", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "uq_verify_files_filename_lower",
        "verify_files",
        [sa.text("lower(filename)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_verify_files_filename_lower", table_name="verify_files")
    op.drop_table("verify_files")
