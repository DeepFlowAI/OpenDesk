"""add knowledge import export permissions

Revision ID: 8e9f0a1b2c3d
Revises: 7d8e9f0a1b2c
Create Date: 2026-06-19
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "8e9f0a1b2c3d"
down_revision: Union[str, Sequence[str], None] = "7d8e9f0a1b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


KNOWLEDGE_IMPORT_EXPORT_PERMISSIONS = {
    "knowledge.workspace.import",
    "knowledge.workspace.export",
}


def _permission_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = json.loads(value)
        return [str(item) for item in loaded]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = 'admin' AND is_system = true")
    ).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        permissions.update(KNOWLEDGE_IMPORT_EXPORT_PERMISSIONS)
        bind.execute(
            sa.text(
                """
                UPDATE roles
                SET permissions = CAST(:permissions AS JSON), updated_at = now()
                WHERE id = :role_id
                """
            ),
            {"role_id": row["id"], "permissions": json.dumps(sorted(permissions))},
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, permissions FROM roles")).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        permissions.difference_update(KNOWLEDGE_IMPORT_EXPORT_PERMISSIONS)
        bind.execute(
            sa.text(
                """
                UPDATE roles
                SET permissions = CAST(:permissions AS JSON), updated_at = now()
                WHERE id = :role_id
                """
            ),
            {"role_id": row["id"], "permissions": json.dumps(sorted(permissions))},
        )
