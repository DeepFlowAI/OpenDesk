"""add open agent conversation state

Revision ID: 4f5a6b7c8d9e
Revises: 3e4f5a6b7c8d
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4f5a6b7c8d9e"
down_revision: Union[str, None] = "3e4f5a6b7c8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("open_agent_agent_id", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("open_agent_agent_name", sa.String(length=128), nullable=True))
    op.add_column("conversations", sa.Column("open_agent_conversation_id", sa.Integer(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("open_agent_conversation_external_id", sa.String(length=128), nullable=True),
    )
    op.add_column("conversations", sa.Column("open_agent_last_request_id", sa.String(length=128), nullable=True))
    op.add_column("conversations", sa.Column("open_agent_last_event_id", sa.String(length=128), nullable=True))
    op.add_column("conversations", sa.Column("open_agent_handoff_state", sa.String(length=32), nullable=True))
    op.add_column(
        "conversations",
        sa.Column(
            "open_agent_handoff_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversations_open_agent_conversation_id",
        "conversations",
        ["tenant_id", "open_agent_conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_open_agent_conversation_id", table_name="conversations")
    op.drop_column("conversations", "open_agent_handoff_payload")
    op.drop_column("conversations", "open_agent_handoff_state")
    op.drop_column("conversations", "open_agent_last_event_id")
    op.drop_column("conversations", "open_agent_last_request_id")
    op.drop_column("conversations", "open_agent_conversation_external_id")
    op.drop_column("conversations", "open_agent_conversation_id")
    op.drop_column("conversations", "open_agent_agent_name")
    op.drop_column("conversations", "open_agent_agent_id")
