"""add auto outbound tasks

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c4
Create Date: 2026-08-07
"""
from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_PERMISSIONS = [
    "engagement.auto_outbound_task.manage",
    "engagement.auto_outbound_task.create",
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
        "auto_outbound_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("template_name", sa.String(length=80), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="draft", nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("voice_flow_id", sa.Integer(), nullable=True),
        sa.Column("voice_flow_name", sa.String(length=80), nullable=True),
        sa.Column("transfer_queue_id", sa.Integer(), nullable=True),
        sa.Column("voicespeed_agent_id", sa.String(length=128), nullable=True),
        sa.Column("voicespeed_agent_name", sa.String(length=128), nullable=True),
        sa.Column("intent_result_field_key", sa.String(length=64), nullable=True),
        sa.Column("queue_id", sa.Integer(), nullable=True),
        sa.Column("pacing_mode", sa.String(length=24), nullable=True),
        sa.Column("dial_ratio", sa.Integer(), nullable=True),
        sa.Column("dial_intensity", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("abandon_rate_limit", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("abandon_prompt", sa.String(length=24), nullable=True),
        sa.Column("wrapup_seconds", sa.Integer(), server_default="60", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("daily_time_windows", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("caller_number_id", sa.String(length=32), nullable=True),
        sa.Column("max_concurrency", sa.Integer(), server_default="10", nullable=False),
        sa.Column("retry_policy", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("daily_per_number_limit", sa.Integer(), server_default="3", nullable=False),
        sa.Column("auto_pause_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["caller_number_id"], ["phone_numbers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["outbound_task_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auto_outbound_tasks_tenant_creator", "auto_outbound_tasks", ["tenant_id", "created_by_id"])
    op.create_index("ix_auto_outbound_tasks_tenant_mode", "auto_outbound_tasks", ["tenant_id", "execution_mode"])
    op.create_index("ix_auto_outbound_tasks_tenant_status", "auto_outbound_tasks", ["tenant_id", "status"])
    op.create_index("ix_auto_outbound_tasks_tenant_updated", "auto_outbound_tasks", ["tenant_id", "updated_at"])

    op.create_table(
        "auto_outbound_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("field_values", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("call_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("answered_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retry_counts", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("last_called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_call_result", sa.String(length=80), nullable=True),
        sa.Column("next_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["auto_outbound_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auto_outbound_targets_next_call_at", "auto_outbound_targets", ["next_call_at"])
    op.create_index("ix_auto_outbound_targets_phone_number", "auto_outbound_targets", ["phone_number"])
    op.create_index("ix_auto_outbound_targets_status", "auto_outbound_targets", ["status"])
    op.create_index("ix_auto_outbound_targets_task_id", "auto_outbound_targets", ["task_id"])
    op.create_index(
        "ix_auto_outbound_targets_task_status_next",
        "auto_outbound_targets",
        ["task_id", "status", "next_call_at"],
    )
    op.create_index("ix_auto_outbound_targets_tenant_task", "auto_outbound_targets", ["tenant_id", "task_id"])

    op.create_table(
        "auto_outbound_call_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.Integer(), nullable=True),
        sa.Column("phone_number", sa.String(length=64), nullable=False),
        sa.Column("attempt_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("terminal_state", sa.String(length=32), nullable=True),
        sa.Column("reception_type", sa.String(length=16), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("reception_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fail_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_id"], ["auto_outbound_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["auto_outbound_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auto_outbound_records_task_id", "auto_outbound_call_records", ["task_id"])
    op.create_index(
        "ix_auto_outbound_records_tenant_target_started",
        "auto_outbound_call_records",
        ["tenant_id", "target_id", "started_at"],
    )
    op.create_index(
        "ix_auto_outbound_records_tenant_task_started",
        "auto_outbound_call_records",
        ["tenant_id", "task_id", "started_at"],
    )

    _append_permissions("admin", ADMIN_PERMISSIONS)


def downgrade() -> None:
    _remove_permissions(ADMIN_PERMISSIONS)
    op.drop_index("ix_auto_outbound_records_tenant_task_started", table_name="auto_outbound_call_records")
    op.drop_index("ix_auto_outbound_records_tenant_target_started", table_name="auto_outbound_call_records")
    op.drop_index("ix_auto_outbound_records_task_id", table_name="auto_outbound_call_records")
    op.drop_table("auto_outbound_call_records")
    op.drop_index("ix_auto_outbound_targets_tenant_task", table_name="auto_outbound_targets")
    op.drop_index("ix_auto_outbound_targets_task_status_next", table_name="auto_outbound_targets")
    op.drop_index("ix_auto_outbound_targets_task_id", table_name="auto_outbound_targets")
    op.drop_index("ix_auto_outbound_targets_status", table_name="auto_outbound_targets")
    op.drop_index("ix_auto_outbound_targets_phone_number", table_name="auto_outbound_targets")
    op.drop_index("ix_auto_outbound_targets_next_call_at", table_name="auto_outbound_targets")
    op.drop_table("auto_outbound_targets")
    op.drop_index("ix_auto_outbound_tasks_tenant_updated", table_name="auto_outbound_tasks")
    op.drop_index("ix_auto_outbound_tasks_tenant_status", table_name="auto_outbound_tasks")
    op.drop_index("ix_auto_outbound_tasks_tenant_mode", table_name="auto_outbound_tasks")
    op.drop_index("ix_auto_outbound_tasks_tenant_creator", table_name="auto_outbound_tasks")
    op.drop_table("auto_outbound_tasks")
