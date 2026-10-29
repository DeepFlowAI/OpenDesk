"""add call event subscription rules

Revision ID: c5e7a9b1d3f5
Revises: a6c8e0f2b4d6
Create Date: 2026-10-22

Additive: call event subscription rules, rule audits, and the admin permission.
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5e7a9b1d3f5"
down_revision: Union[str, Sequence[str], None] = "a6c8e0f2b4d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSION = "call.admin.event_subscription.manage"


def _permission_list(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    return [str(item) for item in value] if isinstance(value, list) else []


def _update_admin_permission(add: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, permissions FROM roles "
            "WHERE key = 'admin' AND is_system = true"
        )
    ).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        if add:
            permissions.add(PERMISSION)
        else:
            permissions.discard(PERMISSION)
        bind.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:permissions AS JSON), "
                "updated_at = now() WHERE id = :role_id"
            ),
            {"role_id": row["id"], "permissions": json.dumps(sorted(permissions))},
        )


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "call_event_subscription_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "event_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "directions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "call_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_employee_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_employee_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["event_subscriptions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_call_event_rule_tenant_name"),
        sa.UniqueConstraint(
            "tenant_id", "subscription_id", name="uq_call_event_rule_tenant_subscription"
        ),
    )
    op.create_index(
        "ix_call_event_rule_tenant_updated",
        "call_event_subscription_rules",
        ["tenant_id", "updated_at"],
    )
    op.create_table(
        "call_event_subscription_rule_audits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("rule_public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_public_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_employee_id", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["actor_employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_call_event_rule_audit_tenant_created",
        "call_event_subscription_rule_audits",
        ["tenant_id", "created_at"],
    )
    _update_admin_permission(True)


def downgrade() -> None:
    _update_admin_permission(False)
    op.drop_index(
        "ix_call_event_rule_audit_tenant_created",
        table_name="call_event_subscription_rule_audits",
    )
    op.drop_table("call_event_subscription_rule_audits")
    op.drop_index(
        "ix_call_event_rule_tenant_updated", table_name="call_event_subscription_rules"
    )
    op.drop_table("call_event_subscription_rules")
