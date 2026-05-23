"""add organization public id

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-20 19:30:00.000000

"""
from typing import Sequence, Union
import secrets

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ORGANIZATION_PUBLIC_ID_PREFIX = "org_"
ORGANIZATION_PUBLIC_ID_RANDOM_LENGTH = 16
ORGANIZATION_PUBLIC_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _organization_public_id() -> str:
    suffix = "".join(
        secrets.choice(ORGANIZATION_PUBLIC_ID_ALPHABET)
        for _ in range(ORGANIZATION_PUBLIC_ID_RANDOM_LENGTH)
    )
    return f"{ORGANIZATION_PUBLIC_ID_PREFIX}{suffix}"


def upgrade() -> None:
    op.add_column("organizations", sa.Column("public_id", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM organizations WHERE public_id IS NULL")).fetchall()
    used: set[str] = set()
    for row in rows:
        value = _organization_public_id()
        while value in used:
            value = _organization_public_id()
        used.add(value)
        bind.execute(
            sa.text("UPDATE organizations SET public_id = :value WHERE id = :id"),
            {"value": value, "id": row[0]},
        )

    op.alter_column("organizations", "public_id", nullable=False)
    op.create_unique_constraint("uq_organizations_public_id", "organizations", ["public_id"])


def downgrade() -> None:
    op.drop_constraint("uq_organizations_public_id", "organizations", type_="unique")
    op.drop_column("organizations", "public_id")
