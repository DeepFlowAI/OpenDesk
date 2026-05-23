"""add public channel and conversation ids

Revision ID: a7c9d8e1f2b3
Revises: 9c1d2e3f4a5b
Create Date: 2026-05-19 19:20:00.000000

"""
from typing import Sequence, Union
import secrets

from alembic import op
import sqlalchemy as sa


revision: str = "a7c9d8e1f2b3"
down_revision: Union[str, None] = "9c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _public_id(prefix: str) -> str:
    return f"{prefix}{secrets.token_urlsafe(24)}"


def _backfill_unique(table_name: str, id_column: str, target_column: str, prefix: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT {id_column} FROM {table_name} WHERE {target_column} IS NULL")).fetchall()
    used: set[str] = set()
    for row in rows:
        value = _public_id(prefix)
        while value in used:
            value = _public_id(prefix)
        used.add(value)
        bind.execute(
            sa.text(f"UPDATE {table_name} SET {target_column} = :value WHERE {id_column} = :id"),
            {"value": value, "id": row[0]},
        )


def upgrade() -> None:
    op.add_column("channels", sa.Column("channel_key", sa.String(length=64), nullable=True))
    op.add_column(
        "channels",
        sa.Column("channel_key_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "channels",
        sa.Column("public_access_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("channels", sa.Column("key_rotated_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("conversations", sa.Column("public_id", sa.String(length=64), nullable=True))

    _backfill_unique("channels", "id", "channel_key", "ch_")
    _backfill_unique("conversations", "id", "public_id", "cv_")

    op.alter_column("channels", "channel_key", nullable=False)
    op.alter_column("conversations", "public_id", nullable=False)

    op.create_unique_constraint("uq_channels_channel_key", "channels", ["channel_key"])
    op.create_unique_constraint("uq_conversations_public_id", "conversations", ["public_id"])


def downgrade() -> None:
    op.drop_constraint("uq_conversations_public_id", "conversations", type_="unique")
    op.drop_constraint("uq_channels_channel_key", "channels", type_="unique")
    op.drop_column("conversations", "public_id")
    op.drop_column("channels", "key_rotated_at")
    op.drop_column("channels", "public_access_enabled")
    op.drop_column("channels", "channel_key_version")
    op.drop_column("channels", "channel_key")
