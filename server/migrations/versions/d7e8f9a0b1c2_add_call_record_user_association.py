"""add call record user association

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-05-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("call_records", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_call_records_user_id_users",
        "call_records",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_cr_tenant_user", "call_records", ["tenant_id", "user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cr_tenant_user", table_name="call_records")
    op.drop_constraint("fk_call_records_user_id_users", "call_records", type_="foreignkey")
    op.drop_column("call_records", "user_id")
