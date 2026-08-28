"""add custom dashboards

Revision ID: e2b4d6f8a0c2
Revises: e1a3c5e7f9b1
Create Date: 2026-08-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e2b4d6f8a0c2"
down_revision: Union[str, Sequence[str], None] = "e1a3c5e7f9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "custom_dashboards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'disabled')",
            name="ck_custom_dashboards_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_custom_dashboards_tenant_name"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_custom_dashboards_tenant_slug"),
    )
    op.create_index(
        "ix_custom_dashboards_tenant_status_sort",
        "custom_dashboards",
        ["tenant_id", "status", "sort_order", "id"],
        unique=False,
    )
    op.create_table(
        "custom_dashboard_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("dashboard_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("icon", sa.String(length=64), server_default="chart-bar", nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "components",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
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
        sa.CheckConstraint(
            "kind IN ('draft', 'published')",
            name="ck_custom_dashboard_versions_kind",
        ),
        sa.ForeignKeyConstraint(
            ["dashboard_id"],
            ["custom_dashboards.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dashboard_id",
            "kind",
            name="uq_custom_dashboard_versions_kind",
        ),
    )
    op.create_index(
        "ix_custom_dashboard_versions_tenant_dashboard",
        "custom_dashboard_versions",
        ["tenant_id", "dashboard_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_custom_dashboard_versions_tenant_dashboard",
        table_name="custom_dashboard_versions",
    )
    op.drop_table("custom_dashboard_versions")
    op.drop_index(
        "ix_custom_dashboards_tenant_status_sort",
        table_name="custom_dashboards",
    )
    op.drop_table("custom_dashboards")
