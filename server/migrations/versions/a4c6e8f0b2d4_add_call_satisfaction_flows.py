"""add call satisfaction flows

Revision ID: a4c6e8f0b2d4
Revises: f3a5c7e9b1d3
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4c6e8f0b2d4"
down_revision: Union[str, None] = "f3a5c7e9b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "satisfaction_flows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_satisfaction_flows_tenant_id",
        "satisfaction_flows",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "uq_satisfaction_flows_one_active_per_tenant",
        "satisfaction_flows",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("enabled IS TRUE AND deleted_at IS NULL"),
    )

    op.create_table(
        "satisfaction_flow_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("satisfaction_flow_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name_snapshot", sa.String(length=50), nullable=False),
        sa.Column("description_snapshot", sa.String(length=200), nullable=True),
        sa.Column("graph_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("question_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("comment", sa.String(length=200), nullable=True),
        sa.Column("created_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("created_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("created_by_actor_name", sa.String(length=128), nullable=True),
        sa.Column("updated_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("updated_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_actor_name", sa.String(length=128), nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["satisfaction_flow_id"], ["satisfaction_flows.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "satisfaction_flow_id", "version_no", name="uq_sfv_flow_version"
        ),
    )
    op.create_index(
        "ix_sfv_tenant_flow",
        "satisfaction_flow_versions",
        ["tenant_id", "satisfaction_flow_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_satisfaction_flows_current_version_id",
        "satisfaction_flows",
        "satisfaction_flow_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_satisfaction_flows_current_version_id",
        "satisfaction_flows",
        type_="foreignkey",
    )
    op.drop_index("ix_sfv_tenant_flow", table_name="satisfaction_flow_versions")
    op.drop_table("satisfaction_flow_versions")
    op.drop_index(
        "uq_satisfaction_flows_one_active_per_tenant",
        table_name="satisfaction_flows",
    )
    op.drop_index("ix_satisfaction_flows_tenant_id", table_name="satisfaction_flows")
    op.drop_table("satisfaction_flows")
