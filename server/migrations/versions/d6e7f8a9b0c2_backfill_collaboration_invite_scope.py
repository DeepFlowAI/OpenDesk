"""backfill collaboration invite data scope

Revision ID: d6e7f8a9b0c2
Revises: a3b5c7d9e1f2, a3c5e7f9b1d4
Create Date: 2026-07-04
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d6e7f8a9b0c2"
down_revision: Union[str, Sequence[str], None] = ("a3b5c7d9e1f2", "a3c5e7f9b1d4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLLABORATION_INVITE_PERMISSION = "chat.conversation.collaboration.invite"
SESSION_RECORD_SCOPE = "session_record"


def _json_dict(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return value if isinstance(value, dict) else {}


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = json.loads(value)
        return [str(item) for item in loaded] if isinstance(loaded, list) else []
    return [str(item) for item in value] if isinstance(value, list) else []


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, permissions, data_scopes FROM roles")).mappings()
    for row in rows:
        permissions = _json_list(row["permissions"])
        if COLLABORATION_INVITE_PERMISSION not in permissions:
            continue

        data_scopes = _json_dict(row["data_scopes"])
        if COLLABORATION_INVITE_PERMISSION in data_scopes:
            continue

        session_scope = data_scopes.get(SESSION_RECORD_SCOPE)
        if session_scope not in {"all", "group", "self"}:
            continue

        data_scopes[COLLABORATION_INVITE_PERMISSION] = session_scope
        bind.execute(
            sa.text(
                """
                UPDATE roles
                SET data_scopes = CAST(:data_scopes AS JSON), updated_at = now()
                WHERE id = :role_id
                """
            ),
            {"role_id": row["id"], "data_scopes": json.dumps(data_scopes)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, data_scopes FROM roles")).mappings()
    for row in rows:
        data_scopes = _json_dict(row["data_scopes"])
        if COLLABORATION_INVITE_PERMISSION not in data_scopes:
            continue

        data_scopes.pop(COLLABORATION_INVITE_PERMISSION, None)
        bind.execute(
            sa.text(
                """
                UPDATE roles
                SET data_scopes = CAST(:data_scopes AS JSON), updated_at = now()
                WHERE id = :role_id
                """
            ),
            {"role_id": row["id"], "data_scopes": json.dumps(data_scopes)},
        )
