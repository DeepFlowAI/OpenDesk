"""normalize user public id length

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-20 18:30:00.000000

"""
from typing import Sequence, Union
import re
import secrets

from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_PUBLIC_ID_PREFIX = "usr_"
USER_PUBLIC_ID_RANDOM_LENGTH = 16
USER_PUBLIC_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
USER_PUBLIC_ID_PATTERN = re.compile(r"^usr_[A-Za-z0-9_-]{16}$")


def _is_valid_user_public_id(value: str | None) -> bool:
    return bool(value and USER_PUBLIC_ID_PATTERN.fullmatch(value))


def _user_public_id() -> str:
    suffix = "".join(secrets.choice(USER_PUBLIC_ID_ALPHABET) for _ in range(USER_PUBLIC_ID_RANDOM_LENGTH))
    return f"{USER_PUBLIC_ID_PREFIX}{suffix}"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, public_id FROM users ORDER BY id")).mappings().all()
    used = {row["public_id"] for row in rows if _is_valid_user_public_id(row["public_id"])}

    for row in rows:
        current = row["public_id"]
        if _is_valid_user_public_id(current):
            continue

        value = _user_public_id()
        while value in used:
            value = _user_public_id()
        used.add(value)

        bind.execute(
            sa.text("UPDATE users SET public_id = :value WHERE id = :id"),
            {"value": value, "id": row["id"]},
        )


def downgrade() -> None:
    # The previous overlong values cannot be reconstructed after normalization.
    pass
