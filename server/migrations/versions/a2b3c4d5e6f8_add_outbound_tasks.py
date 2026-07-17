"""add outbound tasks

Revision ID: a2b3c4d5e6f8
Revises: c9d0e1f2a3b4
Create Date: 2026-07-08
"""
from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a2b3c4d5e6f8"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_PERMISSIONS = [
    "engagement.outbound_task.manage",
    "engagement.outbound_task.create",
    "engagement.outbound_task.execute",
    "engagement.outbound_task.template.manage",
]
AGENT_PERMISSIONS = [
    "engagement.outbound_task.execute",
]


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


def _append_permissions(role_key: str, permissions: list[str]) -> None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = :key AND is_system = true"),
        {"key": role_key},
    ).mappings().first()
    if not row:
        return
    merged = sorted(set(_permission_list(row["permissions"])) | set(permissions))
    bind.execute(
        sa.text("UPDATE roles SET permissions = CAST(:permissions AS JSON), updated_at = now() WHERE id = :id"),
        {"id": row["id"], "permissions": json.dumps(merged)},
    )


def _remove_permissions(permissions: list[str]) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, permissions FROM roles")).mappings()
    for row in rows:
        next_permissions = [
            permission for permission in _permission_list(row["permissions"]) if permission not in permissions
        ]
        bind.execute(
            sa.text("UPDATE roles SET permissions = CAST(:permissions AS JSON), updated_at = now() WHERE id = :id"),
            {"id": row["id"], "permissions": json.dumps(next_permissions)},
        )


def upgrade() -> None:
    op.create_table(
        "outbound_task_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_outbound_task_templates_tenant_name"),
    )
    op.create_index("ix_outbound_task_templates_tenant_updated", "outbound_task_templates", ["tenant_id", "updated_at"])

    op.create_table(
        "outbound_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("template_name", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="draft", nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allow_self_claim", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("default_redial_interval_minutes", sa.Integer(), nullable=True),
        sa.Column("assignment_mode", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("assignee_scope_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["outbound_task_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbound_tasks_tenant_creator", "outbound_tasks", ["tenant_id", "created_by_id"])
    op.create_index("ix_outbound_tasks_tenant_status", "outbound_tasks", ["tenant_id", "status"])
    op.create_index("ix_outbound_tasks_tenant_updated", "outbound_tasks", ["tenant_id", "updated_at"])

    op.create_table(
        "outbound_task_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("field_values", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("call_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("answered_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_call_result", sa.String(length=80), nullable=True),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_talk_duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assignee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["outbound_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbound_targets_tenant_assignee_status", "outbound_task_targets", ["tenant_id", "assignee_id", "status"])
    op.create_index("ix_outbound_targets_tenant_phone", "outbound_task_targets", ["tenant_id", "phone_number"])
    op.create_index("ix_outbound_targets_tenant_task_status", "outbound_task_targets", ["tenant_id", "task_id", "status"])

    op.create_table(
        "outbound_call_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("phone_number", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("answered", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("result", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("field_values", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_id"], ["outbound_task_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["outbound_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbound_records_tenant_agent_started", "outbound_call_records", ["tenant_id", "agent_id", "started_at"])
    op.create_index("ix_outbound_records_tenant_target_started", "outbound_call_records", ["tenant_id", "target_id", "started_at"])
    op.create_index("ix_outbound_records_tenant_task_started", "outbound_call_records", ["tenant_id", "task_id", "started_at"])

    _append_permissions("admin", ADMIN_PERMISSIONS)
    _append_permissions("agent", AGENT_PERMISSIONS)


def downgrade() -> None:
    _remove_permissions(ADMIN_PERMISSIONS)
    op.drop_index("ix_outbound_records_tenant_task_started", table_name="outbound_call_records")
    op.drop_index("ix_outbound_records_tenant_target_started", table_name="outbound_call_records")
    op.drop_index("ix_outbound_records_tenant_agent_started", table_name="outbound_call_records")
    op.drop_table("outbound_call_records")
    op.drop_index("ix_outbound_targets_tenant_task_status", table_name="outbound_task_targets")
    op.drop_index("ix_outbound_targets_tenant_phone", table_name="outbound_task_targets")
    op.drop_index("ix_outbound_targets_tenant_assignee_status", table_name="outbound_task_targets")
    op.drop_table("outbound_task_targets")
    op.drop_index("ix_outbound_tasks_tenant_updated", table_name="outbound_tasks")
    op.drop_index("ix_outbound_tasks_tenant_status", table_name="outbound_tasks")
    op.drop_index("ix_outbound_tasks_tenant_creator", table_name="outbound_tasks")
    op.drop_table("outbound_tasks")
    op.drop_index("ix_outbound_task_templates_tenant_updated", table_name="outbound_task_templates")
    op.drop_table("outbound_task_templates")
