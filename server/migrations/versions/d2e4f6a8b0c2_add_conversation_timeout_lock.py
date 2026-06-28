"""add conversation timeout lock

Revision ID: d2e4f6a8b0c2
Revises: c1d2e3f4a5b6
Create Date: 2026-06-28
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d2e4f6a8b0c2"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TIMEOUT_LOCK_PERMISSION = "chat.conversation.lock"


def _permission_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = json.loads(value)
        return [str(item) for item in loaded]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _add_permission(role_key: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = :role_key AND is_system = true"),
        {"role_key": role_key},
    ).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        permissions.add(TIMEOUT_LOCK_PERMISSION)
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


def _remove_permission() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, permissions FROM roles")).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        permissions.discard(TIMEOUT_LOCK_PERMISSION)
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


def upgrade() -> None:
    op.add_column(
        "visitor_timeout_close_states",
        sa.Column("timeout_locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "visitor_timeout_close_states",
        sa.Column("timeout_locked_by_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_visitor_timeout_close_states_tenant_locked",
        "visitor_timeout_close_states",
        ["tenant_id", "timeout_locked_at"],
        unique=False,
    )
    _add_permission("admin")
    _add_permission("agent")


def downgrade() -> None:
    _remove_permission()
    op.drop_index("ix_visitor_timeout_close_states_tenant_locked", table_name="visitor_timeout_close_states")
    op.drop_column("visitor_timeout_close_states", "timeout_locked_by_id")
    op.drop_column("visitor_timeout_close_states", "timeout_locked_at")
