"""add customer unread offline replies

Revision ID: 7d8e9f0a1b2c
Revises: 6c7d8e9f0a1b
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d8e9f0a1b2c"
down_revision: Union[str, Sequence[str], None] = "6c7d8e9f0a1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("offline_messages", sa.Column("customer_unread_at", sa.DateTime(), nullable=True))
    op.add_column("offline_messages", sa.Column("customer_read_at", sa.DateTime(), nullable=True))
    op.add_column(
        "offline_messages",
        sa.Column("customer_unread_first_message_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_offline_messages_customer_unread_first_message_id_messages",
        "offline_messages",
        "messages",
        ["customer_unread_first_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_offline_messages_customer_unread",
        "offline_messages",
        ["tenant_id", "channel_id", "visitor_external_id", "customer_unread_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_offline_messages_customer_unread", table_name="offline_messages")
    op.drop_constraint(
        "fk_offline_messages_customer_unread_first_message_id_messages",
        "offline_messages",
        type_="foreignkey",
    )
    op.drop_column("offline_messages", "customer_unread_first_message_id")
    op.drop_column("offline_messages", "customer_read_at")
    op.drop_column("offline_messages", "customer_unread_at")
