"""fix auto outbound admin permissions for all tenants

Revision ID: f1a2b3c4d5e7
Revises: e9f0a1b2c3d4
Create Date: 2026-08-07

Idempotent data fix: the previous migration only updated the first system admin
role row. Merge the auto-outbound manage/create permissions onto every
is_system admin role across tenants.
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e7"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_PERMISSIONS = {
    "engagement.auto_outbound_task.manage",
    "engagement.auto_outbound_task.create",
}


def _permission_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = 'admin' AND is_system = true")
    ).mappings()
    for row in rows:
        merged = sorted(set(_permission_list(row["permissions"])) | ADMIN_PERMISSIONS)
        bind.execute(
            sa.text(
                """
                UPDATE roles
                SET permissions = CAST(:permissions AS JSON), updated_at = now()
                WHERE id = :role_id
                """
            ),
            {"role_id": row["id"], "permissions": json.dumps(merged)},
        )


def downgrade() -> None:
    # Keep permissions after downgrade; removing them would break tenants that
    # only received the fix from this revision.
    pass
