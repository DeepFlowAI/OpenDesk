"""add conversation collaboration

Revision ID: 8a1c2e3f4b5d
Revises: 7b8c9d0e1f2a
Create Date: 2026-06-24
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "8a1c2e3f4b5d"
down_revision: Union[str, Sequence[str], None] = "7b8c9d0e1f2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLLABORATION_AGENT_PERMISSIONS = {
    "chat.conversation.collaboration.respond",
    "chat.conversation.collaboration.message.send",
}
COLLABORATION_ALL_PERMISSIONS = {
    "chat.conversation.collaboration.invite",
    *COLLABORATION_AGENT_PERMISSIONS,
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


def _add_permissions(role_key: str, permissions_to_add: set[str]) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = :role_key AND is_system = true"),
        {"role_key": role_key},
    ).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        permissions.update(permissions_to_add)
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
    op.create_table(
        "conversation_collaboration_invitations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("conversation_id", sa.Integer, nullable=False),
        sa.Column("inviter_id", sa.Integer, nullable=True),
        sa.Column("invitee_id", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inviter_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invitee_id"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_collab_inv_tenant_conversation",
        "conversation_collaboration_invitations",
        ["tenant_id", "conversation_id"],
    )
    op.create_index(
        "ix_collab_inv_invitee_status",
        "conversation_collaboration_invitations",
        ["tenant_id", "invitee_id", "status"],
    )
    op.create_index(
        "uq_collab_inv_pending_target",
        "conversation_collaboration_invitations",
        ["tenant_id", "conversation_id", "invitee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "conversation_collaborators",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("conversation_id", sa.Integer, nullable=False),
        sa.Column("agent_id", sa.Integer, nullable=True),
        sa.Column("invitation_id", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invitation_id"], ["conversation_collaboration_invitations.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_collaborators_tenant_conversation_status",
        "conversation_collaborators",
        ["tenant_id", "conversation_id", "status"],
    )
    op.create_index(
        "ix_collaborators_agent_status",
        "conversation_collaborators",
        ["tenant_id", "agent_id", "status"],
    )
    op.create_index(
        "uq_collaborators_active_agent",
        "conversation_collaborators",
        ["tenant_id", "conversation_id", "agent_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    _add_permissions("admin", COLLABORATION_ALL_PERMISSIONS)
    _add_permissions("agent", COLLABORATION_AGENT_PERMISSIONS)


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, permissions FROM roles")).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        permissions.difference_update(COLLABORATION_ALL_PERMISSIONS)
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

    op.drop_index("uq_collaborators_active_agent", table_name="conversation_collaborators")
    op.drop_index("ix_collaborators_agent_status", table_name="conversation_collaborators")
    op.drop_index("ix_collaborators_tenant_conversation_status", table_name="conversation_collaborators")
    op.drop_table("conversation_collaborators")

    op.drop_index("uq_collab_inv_pending_target", table_name="conversation_collaboration_invitations")
    op.drop_index("ix_collab_inv_invitee_status", table_name="conversation_collaboration_invitations")
    op.drop_index("ix_collab_inv_tenant_conversation", table_name="conversation_collaboration_invitations")
    op.drop_table("conversation_collaboration_invitations")
