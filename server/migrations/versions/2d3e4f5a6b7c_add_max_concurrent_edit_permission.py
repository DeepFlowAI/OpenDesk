"""add chat workspace max concurrent edit permission

Revision ID: 2d3e4f5a6b7c
Revises: 1c2d3e4f5a6b
Create Date: 2026-06-18 00:00:00.000000
"""
from typing import Sequence, Union

import json

from alembic import op
import sqlalchemy as sa


revision: str = "2d3e4f5a6b7c"
down_revision: Union[str, Sequence[str], None] = "1c2d3e4f5a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMIN_PERMISSIONS = [
    "chat.workspace.max_concurrent.edit",
]


def _append_permissions(role_key: str, permissions: list[str]) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = :key AND is_system = true"),
        {"key": role_key},
    ).mappings().all()
    for row in rows:
        current = row["permissions"] or []
        if isinstance(current, str):
            current = json.loads(current)
        merged = sorted(set(current) | set(permissions))
        conn.execute(
            sa.text("UPDATE roles SET permissions = CAST(:permissions AS JSON), updated_at = now() WHERE id = :id"),
            {"id": row["id"], "permissions": json.dumps(merged)},
        )


def _remove_permissions(role_key: str, permissions: list[str]) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = :key AND is_system = true"),
        {"key": role_key},
    ).mappings().all()
    for row in rows:
        current = row["permissions"] or []
        if isinstance(current, str):
            current = json.loads(current)
        next_permissions = [permission for permission in current if permission not in permissions]
        conn.execute(
            sa.text("UPDATE roles SET permissions = CAST(:permissions AS JSON), updated_at = now() WHERE id = :id"),
            {"id": row["id"], "permissions": json.dumps(next_permissions)},
        )


def upgrade() -> None:
    _append_permissions("admin", ADMIN_PERMISSIONS)


def downgrade() -> None:
    _remove_permissions("admin", ADMIN_PERMISSIONS)
