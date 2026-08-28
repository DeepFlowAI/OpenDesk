"""add embedded call integrations

Revision ID: a1c3e5f7b9d1
Revises: e8a0b2c4d6f8
Create Date: 2026-08-13 18:30:00.000000
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a1c3e5f7b9d1"
down_revision: Union[str, Sequence[str], None] = "e8a0b2c4d6f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_PERMISSION = "call.admin.embed.manage"
AGENT_PERMISSION = "call.embed.use"


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


def _update_system_permissions(add: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, key, permissions FROM roles "
            "WHERE key IN ('admin', 'agent') AND is_system = true"
        )
    ).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        target = {AGENT_PERMISSION}
        if row["key"] == "admin":
            target.add(ADMIN_PERMISSION)
        if add:
            permissions.update(target)
        else:
            permissions.difference_update(target)
        bind.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:permissions AS JSON), "
                "updated_at = now() WHERE id = :role_id"
            ),
            {"role_id": row["id"], "permissions": json.dumps(sorted(permissions))},
        )


def upgrade() -> None:
    op.create_table(
        "embedded_call_integrations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("integration_key", sa.String(length=48), nullable=False),
        sa.Column(
            "allowed_origins",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("secret_digest", sa.String(length=64), nullable=False),
        sa.Column("secret_last_four", sa.String(length=4), nullable=False),
        sa.Column("secret_rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_secret_digest", sa.String(length=64), nullable=True),
        sa.Column("previous_secret_last_four", sa.String(length=4), nullable=True),
        sa.Column("previous_secret_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_key"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_embedded_call_integrations_tenant_updated",
        "embedded_call_integrations",
        ["tenant_id", "updated_at"],
    )
    _update_system_permissions(True)


def downgrade() -> None:
    _update_system_permissions(False)
    op.drop_index(
        "ix_embedded_call_integrations_tenant_updated",
        table_name="embedded_call_integrations",
    )
    op.drop_table("embedded_call_integrations")
