"""add message client message id

Revision ID: bb22cc33dd44
Revises: aa11bb22cc33
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "bb22cc33dd44"
down_revision: Union[str, Sequence[str], None] = "aa11bb22cc33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("client_message_id", sa.String(length=128), nullable=True))
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                NULLIF(metadata->>'client_message_id', '') AS client_message_id,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        tenant_id,
                        conversation_id,
                        sender_type,
                        COALESCE(sender_id, 0),
                        metadata->>'client_message_id'
                    ORDER BY id
                ) AS duplicate_rank
            FROM messages
            WHERE NULLIF(metadata->>'client_message_id', '') IS NOT NULL
        )
        UPDATE messages
        SET client_message_id = ranked.client_message_id
        FROM ranked
        WHERE messages.id = ranked.id
          AND ranked.duplicate_rank = 1
        """
    )
    op.create_index(
        "uq_messages_client_message_id",
        "messages",
        [
            "tenant_id",
            "conversation_id",
            "sender_type",
            sa.text("COALESCE(sender_id, 0)"),
            "client_message_id",
        ],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_client_message_id", table_name="messages")
    op.drop_column("messages", "client_message_id")
