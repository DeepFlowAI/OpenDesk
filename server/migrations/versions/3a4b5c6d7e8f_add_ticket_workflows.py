"""add ticket workflows

Revision ID: 3a4b5c6d7e8f
Revises: 2b3c4d5e6f7a
Create Date: 2026-06-02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "3a4b5c6d7e8f"
down_revision: Union[str, Sequence[str], None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_workflows",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_version_id", sa.Integer, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_workflows_tenant_sort",
        "ticket_workflows",
        ["tenant_id", "sort_order", "id"],
    )
    op.create_index(
        "ix_ticket_workflows_tenant_enabled",
        "ticket_workflows",
        ["tenant_id", "enabled"],
    )

    op.create_table(
        "ticket_workflow_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("workflow_id", sa.Integer, nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("graph_json", JSONB, nullable=False),
        sa.Column("comment", sa.String(200), nullable=True),
        sa.Column("created_by_actor_type", sa.String(32), nullable=True),
        sa.Column("created_by_actor_id", sa.Integer, nullable=True),
        sa.Column("created_by_actor_name", sa.String(128), nullable=True),
        sa.Column("updated_by_actor_type", sa.String(32), nullable=True),
        sa.Column("updated_by_actor_id", sa.Integer, nullable=True),
        sa.Column("updated_by_actor_name", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["ticket_workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "version_no", name="uq_twv_workflow_version"),
    )
    op.create_index(
        "ix_twv_tenant_workflow",
        "ticket_workflow_versions",
        ["tenant_id", "workflow_id"],
    )
    op.create_foreign_key(
        "fk_ticket_workflows_current_version",
        "ticket_workflows",
        "ticket_workflow_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_ticket_workflows_current_version", "ticket_workflows", type_="foreignkey")
    op.drop_index("ix_twv_tenant_workflow", table_name="ticket_workflow_versions")
    op.drop_table("ticket_workflow_versions")
    op.drop_index("ix_ticket_workflows_tenant_enabled", table_name="ticket_workflows")
    op.drop_index("ix_ticket_workflows_tenant_sort", table_name="ticket_workflows")
    op.drop_table("ticket_workflows")
