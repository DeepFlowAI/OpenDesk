"""add sms bulk task tables

Revision ID: c5d6e7f8a9b0
Revises: e3f5a7b9c1d2, f1a2b3c4d5e7
Create Date: 2026-08-08 09:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = ("e3f5a7b9c1d2", "f1a2b3c4d5e7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMIN_PERMISSIONS = [
    "engagement.sms_task.manage",
    "engagement.sms_task.create",
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
    rows = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key = :key AND is_system = true"),
        {"key": role_key},
    ).mappings()
    for row in rows:
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
        "sms_bulk_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("template_name", sa.String(length=64), nullable=False),
        sa.Column("template_type", sa.String(length=16), nullable=False),
        sa.Column("sign_name", sa.String(length=64), nullable=False),
        sa.Column("provider_sign_name", sa.String(length=128), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_template_code", sa.String(length=64), nullable=False),
        sa.Column("send_type", sa.String(length=16), server_default="immediate", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pause_reason", sa.String(length=32), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["sms_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_bulk_tasks_tenant_status", "sms_bulk_tasks", ["tenant_id", "status"], unique=False)
    op.create_index("ix_sms_bulk_tasks_tenant_updated", "sms_bulk_tasks", ["tenant_id", "updated_at"], unique=False)
    op.create_index("ix_sms_bulk_tasks_tenant_creator", "sms_bulk_tasks", ["tenant_id", "created_by_id"], unique=False)
    op.create_index("ix_sms_bulk_tasks_scheduled", "sms_bulk_tasks", ["status", "scheduled_at"], unique=False)

    op.add_column("sms_send_records", sa.Column("source", sa.String(length=16), server_default="single", nullable=False))
    op.add_column("sms_send_records", sa.Column("bulk_task_id", sa.Integer(), nullable=True))
    op.alter_column("sms_send_records", "employee_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        "fk_sms_send_records_bulk_task_id",
        "sms_send_records",
        "sms_bulk_tasks",
        ["bulk_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sms_send_records_tenant_source", "sms_send_records", ["tenant_id", "source"], unique=False)

    op.create_table(
        "sms_bulk_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("variable_values", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("fail_reason", sa.String(length=255), nullable=True),
        sa.Column("send_record_id", sa.Integer(), nullable=True),
        sa.Column("provider_biz_id", sa.String(length=128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["send_record_id"], ["sms_send_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["sms_bulk_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "phone", name="uq_sms_bulk_targets_task_phone"),
    )
    op.create_index(
        "ix_sms_bulk_targets_tenant_task_status", "sms_bulk_targets", ["tenant_id", "task_id", "status"], unique=False
    )
    op.create_index("ix_sms_bulk_targets_task_status", "sms_bulk_targets", ["task_id", "status"], unique=False)
    op.create_index("ix_sms_bulk_targets_send_record", "sms_bulk_targets", ["send_record_id"], unique=False)

    _append_permissions("admin", ADMIN_PERMISSIONS)


def downgrade() -> None:
    _remove_permissions(ADMIN_PERMISSIONS)
    op.drop_index("ix_sms_bulk_targets_send_record", table_name="sms_bulk_targets")
    op.drop_index("ix_sms_bulk_targets_task_status", table_name="sms_bulk_targets")
    op.drop_index("ix_sms_bulk_targets_tenant_task_status", table_name="sms_bulk_targets")
    op.drop_table("sms_bulk_targets")
    op.drop_index("ix_sms_send_records_tenant_source", table_name="sms_send_records")
    op.drop_constraint("fk_sms_send_records_bulk_task_id", "sms_send_records", type_="foreignkey")
    op.alter_column("sms_send_records", "employee_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("sms_send_records", "bulk_task_id")
    op.drop_column("sms_send_records", "source")
    op.drop_index("ix_sms_bulk_tasks_scheduled", table_name="sms_bulk_tasks")
    op.drop_index("ix_sms_bulk_tasks_tenant_creator", table_name="sms_bulk_tasks")
    op.drop_index("ix_sms_bulk_tasks_tenant_updated", table_name="sms_bulk_tasks")
    op.drop_index("ix_sms_bulk_tasks_tenant_status", table_name="sms_bulk_tasks")
    op.drop_table("sms_bulk_tasks")
