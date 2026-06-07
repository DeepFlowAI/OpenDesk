"""add roles

Revision ID: 4b5c6d7e8f90
Revises: 3a4b5c6d7e8f
Create Date: 2026-06-07 00:00:00.000000

"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa


revision: str = "4b5c6d7e8f90"
down_revision: Union[str, Sequence[str], None] = "3a4b5c6d7e8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ALL_PERMISSION_KEYS = [
    "admin.access",
    "call.admin.flow.manage",
    "call.admin.number.manage",
    "call.admin.summary_config.manage",
    "call.monitor.view",
    "call.record.export",
    "call.record.view",
    "call.report.export",
    "call.report.view",
    "call.workspace.use",
    "chat.admin.channel.manage",
    "chat.admin.routing.manage",
    "chat.admin.satisfaction.manage",
    "chat.admin.settings.manage",
    "chat.admin.summary_config.manage",
    "chat.conversation.transfer",
    "chat.online_monitor.view",
    "chat.session_record.export",
    "chat.session_record.view",
    "chat.session_report.export",
    "chat.session_report.view",
    "chat.workspace.use",
    "crm.admin.org_field.manage",
    "crm.admin.org_settings.manage",
    "crm.admin.org_view.manage",
    "crm.admin.user_field.manage",
    "crm.admin.user_view.manage",
    "crm.workspace.org.create",
    "crm.workspace.org.delete",
    "crm.workspace.org.edit",
    "crm.workspace.org.view",
    "crm.workspace.user.create",
    "crm.workspace.user.delete",
    "crm.workspace.user.edit",
    "crm.workspace.user.view",
    "org.employee.create",
    "org.employee.delete",
    "org.employee.edit",
    "org.employee.view",
    "org.group.manage",
    "org.queue.manage",
    "org.role.manage",
    "settings.open_agent.manage",
    "settings.service_hours.manage",
    "settings.system.manage",
    "ticket.admin.layout.manage",
    "ticket.admin.shared_field.manage",
    "ticket.admin.view.manage",
    "ticket.admin.workflow.manage",
    "ticket.workspace.comment",
    "ticket.workspace.create",
    "ticket.workspace.delete",
    "ticket.workspace.edit",
    "ticket.workspace.export",
    "ticket.workspace.view",
]

AGENT_PERMISSION_KEYS = [
    "chat.workspace.use",
    "call.workspace.use",
    "ticket.workspace.view",
    "ticket.workspace.create",
    "ticket.workspace.edit",
    "ticket.workspace.comment",
    "crm.workspace.user.view",
    "crm.workspace.org.view",
    "chat.session_record.view",
    "call.record.view",
    "chat.conversation.transfer",
]

ADMIN_DATA_SCOPES = {"call_record": "all", "session_record": "all", "ticket": "all"}
AGENT_DATA_SCOPES = {"call_record": "self", "session_record": "self", "ticket": "self"}


def _seed_system_role(
    key: str,
    name: str,
    description: str,
    permissions: list[str],
    data_scopes: dict[str, str],
) -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO roles (
                tenant_id, key, name, description, is_system, is_active,
                permissions, data_scopes, created_at, updated_at
            )
            SELECT
                tenants.id, :key, :name, :description, true, true,
                CAST(:permissions AS JSON), CAST(:data_scopes AS JSON), now(), now()
            FROM tenants
            ON CONFLICT (tenant_id, key) DO UPDATE SET
                is_system = true,
                is_active = true,
                permissions = EXCLUDED.permissions,
                data_scopes = EXCLUDED.data_scopes,
                updated_at = now()
            """
        ),
        {
            "key": key,
            "name": name,
            "description": description,
            "permissions": json.dumps(permissions),
            "data_scopes": json.dumps(data_scopes),
        },
    )


def _backfill_employee_role(key: str) -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO employee_roles (employee_id, role_id, created_at)
            SELECT employees.id, roles.id, now()
            FROM employees
            JOIN roles ON roles.tenant_id = employees.tenant_id AND roles.key = :key
            WHERE CAST(employees.roles AS JSONB) ? :key
            ON CONFLICT (employee_id, role_id) DO NOTHING
            """
        ),
        {"key": key},
    )


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("permissions", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("data_scopes", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_roles_tenant_key"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )
    op.create_index("ix_roles_tenant_active", "roles", ["tenant_id", "is_active"], unique=False)
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"], unique=False)

    op.create_table(
        "employee_roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "role_id", name="uq_employee_roles_employee_role"),
    )
    op.create_index("ix_employee_roles_employee_id", "employee_roles", ["employee_id"], unique=False)
    op.create_index("ix_employee_roles_role_id", "employee_roles", ["role_id"], unique=False)

    _seed_system_role(
        "admin",
        "管理员",
        "系统内置管理员角色",
        ALL_PERMISSION_KEYS,
        ADMIN_DATA_SCOPES,
    )
    _seed_system_role(
        "agent",
        "客服",
        "系统内置客服角色",
        AGENT_PERMISSION_KEYS,
        AGENT_DATA_SCOPES,
    )
    _backfill_employee_role("admin")
    _backfill_employee_role("agent")


def downgrade() -> None:
    op.drop_index("ix_employee_roles_role_id", table_name="employee_roles")
    op.drop_index("ix_employee_roles_employee_id", table_name="employee_roles")
    op.drop_table("employee_roles")
    op.drop_index("ix_roles_tenant_id", table_name="roles")
    op.drop_index("ix_roles_tenant_active", table_name="roles")
    op.drop_table("roles")
