"""add robot QA settings

Revision ID: 44d667f1c990
Revises: 33c556e0b889
Create Date: 2026-07-15 15:00:00.000000
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "44d667f1c990"
down_revision: Union[str, Sequence[str], None] = "33c556e0b889"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROBOT_QA_PERMISSION = "chat.conversation.robot_qa.create"


def _permission_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = json.loads(value)
        return [str(item) for item in loaded] if isinstance(loaded, list) else []
    return [str(item) for item in value] if isinstance(value, list) else []


def _update_system_role_permissions(add: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key IN ('admin', 'agent') AND is_system = true")
    ).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        if add:
            permissions.add(ROBOT_QA_PERMISSION)
        else:
            permissions.discard(ROBOT_QA_PERMISSION)
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
        "open_agent_settings",
        sa.Column("robot_qa_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "open_agent_settings",
        sa.Column("robot_qa_knowledge_base_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "open_agent_settings",
        sa.Column("robot_qa_knowledge_base_name", sa.String(length=255), nullable=True),
    )
    _update_system_role_permissions(True)


def downgrade() -> None:
    _update_system_role_permissions(False)
    op.drop_column("open_agent_settings", "robot_qa_knowledge_base_name")
    op.drop_column("open_agent_settings", "robot_qa_knowledge_base_id")
    op.drop_column("open_agent_settings", "robot_qa_enabled")
