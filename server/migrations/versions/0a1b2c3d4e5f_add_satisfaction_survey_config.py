"""add satisfaction survey config

Revision ID: 0a1b2c3d4e5f
Revises: f7a8b9c0d1e2
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "satisfaction_survey_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=True),
        sa.Column("triggers", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("service_settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("product_settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_satisfaction_survey_configs_tenant_id"),
    )
    op.create_index(
        "ix_satisfaction_survey_configs_tenant_id",
        "satisfaction_survey_configs",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "satisfaction_survey_config_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("config_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_name", sa.String(length=128), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["config_id"], ["satisfaction_survey_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "version", name="uq_satisfaction_survey_versions_tenant_version"),
    )
    op.create_index(
        "ix_satisfaction_survey_versions_tenant_published",
        "satisfaction_survey_config_versions",
        ["tenant_id", "published_at"],
        unique=False,
    )
    op.create_index(
        "ix_satisfaction_survey_versions_config_version",
        "satisfaction_survey_config_versions",
        ["config_id", "version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_satisfaction_survey_versions_config_version", table_name="satisfaction_survey_config_versions")
    op.drop_index("ix_satisfaction_survey_versions_tenant_published", table_name="satisfaction_survey_config_versions")
    op.drop_table("satisfaction_survey_config_versions")
    op.drop_index("ix_satisfaction_survey_configs_tenant_id", table_name="satisfaction_survey_configs")
    op.drop_table("satisfaction_survey_configs")
