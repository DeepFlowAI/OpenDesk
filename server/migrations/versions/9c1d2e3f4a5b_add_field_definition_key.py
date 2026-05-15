"""add field definition key

Revision ID: 9c1d2e3f4a5b
Revises: 8b3f2c4d5e6a
Create Date: 2026-05-11 21:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c1d2e3f4a5b"
down_revision: Union[str, None] = "8b3f2c4d5e6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fd_field_definitions",
        sa.Column("field_key", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE fd_field_definitions
        SET field_key = id::text
        WHERE field_key IS NULL OR field_key = ''
        """,
    )
    op.alter_column("fd_field_definitions", "field_key", nullable=False)
    op.create_unique_constraint(
        "uq_fd_field_defs_tenant_domain_field_key",
        "fd_field_definitions",
        ["tenant_id", "domain", "field_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_fd_field_defs_tenant_domain_field_key",
        "fd_field_definitions",
        type_="unique",
    )
    op.drop_column("fd_field_definitions", "field_key")
