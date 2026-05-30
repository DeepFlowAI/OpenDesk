"""add call summary config

Revision ID: 5a6b7c8d9e0f
Revises: 4f5a6b7c8d9e
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "5a6b7c8d9e0f"
down_revision: Union[str, None] = "4f5a6b7c8d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_summary_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_call_summary_configs_tenant"),
    )

    op.create_table(
        "call_summary_config_fields",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("config_id", sa.Integer(), nullable=False),
        sa.Column("field_definition_id", sa.Integer(), nullable=True),
        sa.Column("field_key", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["config_id"], ["call_summary_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_definition_id"], ["fd_field_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("config_id", "field_definition_id", name="uq_call_summary_cfg_field_def"),
        sa.UniqueConstraint("config_id", "field_key", name="uq_call_summary_cfg_field_key"),
    )
    op.create_index(
        "ix_call_summary_config_fields_config",
        "call_summary_config_fields",
        ["config_id"],
        unique=False,
    )

    op.create_table(
        "call_summary_interaction_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("config_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("condition_logic", sa.String(length=8), server_default="and", nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("actions", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["config_id"], ["call_summary_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_call_summary_interaction_rules_config",
        "call_summary_interaction_rules",
        ["config_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_call_summary_interaction_rules_config", table_name="call_summary_interaction_rules")
    op.drop_table("call_summary_interaction_rules")
    op.drop_index("ix_call_summary_config_fields_config", table_name="call_summary_config_fields")
    op.drop_table("call_summary_config_fields")
    op.drop_table("call_summary_configs")
