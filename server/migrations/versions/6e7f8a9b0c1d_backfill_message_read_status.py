"""backfill message read status

Revision ID: 6e7f8a9b0c1d
Revises: 5d6e7f8a9b0c
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "6e7f8a9b0c1d"
down_revision: Union[str, Sequence[str], None] = "5d6e7f8a9b0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE messages
        SET visitor_read_at = created_at
        WHERE sender_type = 'agent'
          AND content_type IN ('text', 'rich_text', 'image', 'file')
          AND visitor_read_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE messages
        SET agent_read_at = created_at
        WHERE sender_type = 'visitor'
          AND content_type IN ('text', 'rich_text', 'image', 'file')
          AND agent_read_at IS NULL
        """
    )


def downgrade() -> None:
    pass
