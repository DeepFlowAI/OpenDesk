"""add auto outbound event subscriptions

Revision ID: c9e1f3a5b7d9
Revises: b8d0f2a4c6e8
Create Date: 2026-08-25

Additive: task webhook bindings, configuration audits and envelope metadata.
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9e1f3a5b7d9"
down_revision: Union[str, Sequence[str], None] = "b8d0f2a4c6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSION = "engagement.auto_outbound_task.subscription.manage"


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


def upgrade() -> None:
    op.add_column(
        "event_deliveries",
        sa.Column("api_version", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "event_deliveries",
        sa.Column("subject", sa.String(length=256), nullable=True),
    )
    op.create_table(
        "auto_outbound_event_subscriptions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "subscription_public_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "event_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("created_by_employee_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_employee_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["created_by_employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["event_subscriptions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["auto_outbound_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["updated_by_employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", name="uq_auto_outbound_event_subscriptions_task"
        ),
    )
    op.create_index(
        "ix_auto_outbound_event_subscriptions_tenant_task",
        "auto_outbound_event_subscriptions",
        ["tenant_id", "task_id"],
    )
    op.create_index(
        "ix_auto_outbound_event_subscriptions_tenant_subscription",
        "auto_outbound_event_subscriptions",
        ["tenant_id", "subscription_public_id"],
    )
    op.create_table(
        "auto_outbound_event_subscription_audits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("task_public_id", sa.Integer(), nullable=False),
        sa.Column(
            "subscription_public_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_employee_id", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["actor_employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["auto_outbound_tasks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auto_outbound_event_subscription_audits_tenant_task_created",
        "auto_outbound_event_subscription_audits",
        ["tenant_id", "task_public_id", "created_at"],
    )
    _update_admin_permission(True)


def downgrade() -> None:
    _update_admin_permission(False)
    op.drop_index(
        "ix_auto_outbound_event_subscription_audits_tenant_task_created",
        table_name="auto_outbound_event_subscription_audits",
    )
    op.drop_table("auto_outbound_event_subscription_audits")
    op.drop_index(
        "ix_auto_outbound_event_subscriptions_tenant_subscription",
        table_name="auto_outbound_event_subscriptions",
    )
    op.drop_index(
        "ix_auto_outbound_event_subscriptions_tenant_task",
        table_name="auto_outbound_event_subscriptions",
    )
    op.drop_table("auto_outbound_event_subscriptions")
    op.drop_column("event_deliveries", "subject")
    op.drop_column("event_deliveries", "api_version")
