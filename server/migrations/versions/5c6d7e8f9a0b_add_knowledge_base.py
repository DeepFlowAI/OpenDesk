"""add knowledge base

Revision ID: 5c6d7e8f9a0b
Revises: 4b5c6d7e8f90
Create Date: 2026-06-15
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5c6d7e8f9a0b"
down_revision: Union[str, Sequence[str], None] = "4b5c6d7e8f90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


KNOWLEDGE_PERMISSION_KEYS = [
    "knowledge.workspace.view",
    "knowledge.workspace.document.create",
    "knowledge.workspace.document.edit",
    "knowledge.workspace.document.delete",
    "knowledge.workspace.directory.manage",
]


def _sync_system_role_permissions() -> None:
    bind = op.get_bind()
    admin_permissions = [
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
        *KNOWLEDGE_PERMISSION_KEYS,
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
    agent_permissions = [
        "call.record.view",
        "call.workspace.use",
        "chat.conversation.transfer",
        "chat.session_record.view",
        "chat.workspace.use",
        "crm.workspace.org.view",
        "crm.workspace.user.view",
        "knowledge.workspace.view",
        "ticket.workspace.comment",
        "ticket.workspace.create",
        "ticket.workspace.edit",
        "ticket.workspace.view",
    ]
    bind.execute(
        sa.text(
            """
            UPDATE roles
            SET permissions = CAST(:permissions AS JSON), updated_at = now()
            WHERE key = 'admin' AND is_system = true
            """
        ),
        {"permissions": json.dumps(sorted(set(admin_permissions)))},
    )
    bind.execute(
        sa.text(
            """
            UPDATE roles
            SET permissions = CAST(:permissions AS JSON), updated_at = now()
            WHERE key = 'agent' AND is_system = true
            """
        ),
        {"permissions": json.dumps(sorted(set(agent_permissions)))},
    )


def upgrade() -> None:
    op.create_table(
        "knowledge_directories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("created_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("created_by_actor_name", sa.String(length=128), nullable=True),
        sa.Column("updated_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("updated_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_actor_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["knowledge_directories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_directories_tenant_parent",
        "knowledge_directories",
        ["tenant_id", "parent_id"],
    )
    op.create_index(
        "uq_knowledge_directories_tenant_root_name",
        "knowledge_directories",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
    )
    op.create_index(
        "uq_knowledge_directories_tenant_parent_name",
        "knowledge_directories",
        ["tenant_id", "parent_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("directory_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False),
        sa.Column("content_plain", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("validity_type", sa.String(length=16), server_default="permanent", nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("created_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("created_by_actor_name", sa.String(length=128), nullable=True),
        sa.Column("updated_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("updated_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_actor_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["directory_id"], ["knowledge_directories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_documents_tenant_directory",
        "knowledge_documents",
        ["tenant_id", "directory_id"],
    )
    op.create_index(
        "ix_knowledge_documents_tenant_updated",
        "knowledge_documents",
        ["tenant_id", "updated_at"],
    )
    op.create_index(
        "uq_knowledge_documents_tenant_directory_title",
        "knowledge_documents",
        ["tenant_id", "directory_id", "title"],
        unique=True,
    )
    _sync_system_role_permissions()


def downgrade() -> None:
    op.drop_index("uq_knowledge_documents_tenant_directory_title", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_tenant_updated", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_tenant_directory", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("uq_knowledge_directories_tenant_parent_name", table_name="knowledge_directories")
    op.drop_index("uq_knowledge_directories_tenant_root_name", table_name="knowledge_directories")
    op.drop_index("ix_knowledge_directories_tenant_parent", table_name="knowledge_directories")
    op.drop_table("knowledge_directories")
