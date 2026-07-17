"""add knowledge inspirations

Revision ID: b2c4d6e8f0a2
Revises: a1b2c3d4e5f7
Create Date: 2026-07-04
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c4d6e8f0a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMIN_PERMISSIONS = {
    "knowledge.workspace.inspiration.view",
    "knowledge.workspace.inspiration.create",
    "knowledge.workspace.inspiration.manage",
}
AGENT_PERMISSIONS = ADMIN_PERMISSIONS


def _permission_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [str(item) for item in json.loads(value)]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _append_permissions(role_key: str, permissions: set[str]) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = :key AND is_system = true"),
        {"key": role_key},
    ).mappings()
    for row in rows:
        current = set(_permission_list(row["permissions"]))
        current.update(permissions)
        bind.execute(
            sa.text(
                """
                UPDATE roles
                SET permissions = CAST(:permissions AS JSON), updated_at = now()
                WHERE id = :role_id
                """
            ),
            {"role_id": row["id"], "permissions": json.dumps(sorted(current))},
        )


def _remove_permissions(permissions: set[str]) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, permissions FROM roles")).mappings()
    for row in rows:
        current = set(_permission_list(row["permissions"]))
        current.difference_update(permissions)
        bind.execute(
            sa.text(
                """
                UPDATE roles
                SET permissions = CAST(:permissions AS JSON), updated_at = now()
                WHERE id = :role_id
                """
            ),
            {"role_id": row["id"], "permissions": json.dumps(sorted(current))},
        )


def upgrade() -> None:
    op.create_table(
        "knowledge_inspirations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False),
        sa.Column("content_plain", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("source_conversation_id", sa.Integer(), nullable=True),
        sa.Column("source_message_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("created_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("created_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("created_by_actor_name", sa.String(length=128), nullable=True),
        sa.Column("updated_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("updated_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_actor_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'archived', 'document_created')",
            name="ck_knowledge_inspirations_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_inspirations_tenant_status_created",
        "knowledge_inspirations",
        ["tenant_id", "status", "created_at"],
    )
    op.create_index(
        "ix_knowledge_inspirations_tenant_created",
        "knowledge_inspirations",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_knowledge_inspirations_tenant_source_message",
        "knowledge_inspirations",
        ["tenant_id", "source_message_id"],
    )
    op.create_index(
        "ix_knowledge_inspirations_tenant_source_conversation",
        "knowledge_inspirations",
        ["tenant_id", "source_conversation_id"],
    )

    _append_permissions("admin", ADMIN_PERMISSIONS)
    _append_permissions("agent", AGENT_PERMISSIONS)


def downgrade() -> None:
    _remove_permissions(ADMIN_PERMISSIONS)
    op.drop_index("ix_knowledge_inspirations_tenant_source_conversation", table_name="knowledge_inspirations")
    op.drop_index("ix_knowledge_inspirations_tenant_source_message", table_name="knowledge_inspirations")
    op.drop_index("ix_knowledge_inspirations_tenant_created", table_name="knowledge_inspirations")
    op.drop_index("ix_knowledge_inspirations_tenant_status_created", table_name="knowledge_inspirations")
    op.drop_table("knowledge_inspirations")
