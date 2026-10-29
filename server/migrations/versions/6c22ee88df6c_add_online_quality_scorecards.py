"""add online quality scorecards

Revision ID: 6c22ee88df6c
Revises: 5b11dd77ce5b
Create Date: 2026-09-02
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6c22ee88df6c"
down_revision: Union[str, None] = "5b11dd77ce5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quality_scorecards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("current_version_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_scorecards_tenant_status_updated",
        "quality_scorecards",
        ["tenant_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_quality_scorecards_tenant_name", "quality_scorecards", ["tenant_id", "name"]
    )
    op.create_table(
        "quality_scorecard_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scorecard_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("pass_score", sa.Numeric(precision=5, scale=1), server_default="80", nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["scorecard_id"], ["quality_scorecards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scorecard_id", "version_number", name="uq_quality_scorecard_version"),
    )
    op.create_index(
        "uq_quality_scorecard_single_draft",
        "quality_scorecard_versions",
        ["scorecard_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_table(
        "quality_scorecard_sections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["quality_scorecard_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "sort_order", name="uq_quality_scorecard_section_order"),
    )
    op.create_table(
        "quality_scorecard_criteria",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("stable_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rubric", sa.String(length=2000), nullable=False),
        sa.Column("max_points", sa.Numeric(precision=6, scale=2), server_default="10", nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("evidence_policy", sa.String(length=24), server_default="issue_only", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["section_id"], ["quality_scorecard_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("section_id", "sort_order", name="uq_quality_scorecard_criterion_order"),
    )
    op.create_index(
        "ix_quality_scorecard_criteria_stable_key",
        "quality_scorecard_criteria",
        ["stable_key"],
    )
    op.create_table(
        "quality_scorecard_options",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("criterion_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("points", sa.Numeric(precision=6, scale=2), server_default="0", nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="normal", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["criterion_id"], ["quality_scorecard_criteria.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("criterion_id", "sort_order", name="uq_quality_scorecard_option_order"),
    )


def downgrade() -> None:
    op.drop_table("quality_scorecard_options")
    op.drop_index("ix_quality_scorecard_criteria_stable_key", table_name="quality_scorecard_criteria")
    op.drop_table("quality_scorecard_criteria")
    op.drop_table("quality_scorecard_sections")
    op.drop_index("uq_quality_scorecard_single_draft", table_name="quality_scorecard_versions")
    op.drop_table("quality_scorecard_versions")
    op.drop_index("ix_quality_scorecards_tenant_name", table_name="quality_scorecards")
    op.drop_index("ix_quality_scorecards_tenant_status_updated", table_name="quality_scorecards")
    op.drop_table("quality_scorecards")
