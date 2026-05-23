"""add conversation share code

Revision ID: d5e6f7a8b9c0
Revises: c4e5f6a7b8c9
Create Date: 2026-05-20 18:30:00.000000

"""
from typing import Sequence, Union
import secrets

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONVERSATION_SHARE_CODE_PREFIX = "CV-"
CONVERSATION_SHARE_CODE_RANDOM_LENGTH = 8
CONVERSATION_SHARE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _share_code() -> str:
    suffix = "".join(
        secrets.choice(CONVERSATION_SHARE_CODE_ALPHABET)
        for _ in range(CONVERSATION_SHARE_CODE_RANDOM_LENGTH)
    )
    return f"{CONVERSATION_SHARE_CODE_PREFIX}{suffix}"


def upgrade() -> None:
    op.add_column("conversations", sa.Column("share_code", sa.String(length=16), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM conversations WHERE share_code IS NULL")).fetchall()
    used: set[str] = set()
    for row in rows:
        value = _share_code()
        while value in used:
            value = _share_code()
        used.add(value)
        bind.execute(
            sa.text("UPDATE conversations SET share_code = :value WHERE id = :id"),
            {"value": value, "id": row[0]},
        )

    op.alter_column("conversations", "share_code", nullable=False)
    op.create_unique_constraint("uq_conversations_share_code", "conversations", ["share_code"])


def downgrade() -> None:
    op.drop_constraint("uq_conversations_share_code", "conversations", type_="unique")
    op.drop_column("conversations", "share_code")
