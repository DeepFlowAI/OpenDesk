"""add ticket call record link

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-05-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("call_record_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_call_record_id_call_records",
        "tickets",
        "call_records",
        ["call_record_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tickets_call_record", "tickets", ["call_record_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tickets_call_record", table_name="tickets")
    op.drop_constraint("fk_tickets_call_record_id_call_records", "tickets", type_="foreignkey")
    op.drop_column("tickets", "call_record_id")
