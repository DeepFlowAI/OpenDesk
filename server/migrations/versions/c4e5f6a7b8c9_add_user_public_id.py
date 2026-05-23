"""add user public id

Revision ID: c4e5f6a7b8c9
Revises: b8d2f4e6a9c1
Create Date: 2026-05-20 12:00:00.000000

"""
from typing import Sequence, Union
import secrets

from alembic import op
import sqlalchemy as sa


revision: str = "c4e5f6a7b8c9"
down_revision: Union[str, None] = "b8d2f4e6a9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_PUBLIC_ID_PREFIX = "usr_"
USER_PUBLIC_ID_RANDOM_LENGTH = 16
USER_PUBLIC_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _user_public_id() -> str:
    suffix = "".join(secrets.choice(USER_PUBLIC_ID_ALPHABET) for _ in range(USER_PUBLIC_ID_RANDOM_LENGTH))
    return f"{USER_PUBLIC_ID_PREFIX}{suffix}"


def upgrade() -> None:
    op.add_column("users", sa.Column("public_id", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM users WHERE public_id IS NULL")).fetchall()
    used: set[str] = set()
    for row in rows:
        value = _user_public_id()
        while value in used:
            value = _user_public_id()
        used.add(value)
        bind.execute(
            sa.text("UPDATE users SET public_id = :value WHERE id = :id"),
            {"value": value, "id": row[0]},
        )

    op.alter_column("users", "public_id", nullable=False)
    op.create_unique_constraint("uq_users_public_id", "users", ["public_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_public_id", "users", type_="unique")
    op.drop_column("users", "public_id")
