"""add online quality plans

Revision ID: 7d33ff99ea7d
Revises: 6c22ee88df6c
Create Date: 2026-09-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "7d33ff99ea7d"
down_revision: Union[str, None] = "6c22ee88df6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quality_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False), sa.Column("description", sa.String(500), nullable=True),
        sa.Column("run_mode", sa.String(16), server_default="continuous", nullable=False), sa.Column("status", sa.String(24), server_default="draft", nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True), sa.Column("range_start_at", sa.DateTime(timezone=True), nullable=True), sa.Column("range_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("group_ids", postgresql.JSONB(), server_default="[]", nullable=False), sa.Column("agent_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("coverage_mode", sa.String(16), server_default="all", nullable=False), sa.Column("sample_rate", sa.Numeric(5, 2), server_default="100", nullable=False),
        sa.Column("scorecard_version_id", sa.Integer(), nullable=False), sa.Column("execution_strategy", sa.String(16), server_default="ai", nullable=False),
        sa.Column("manual_route_severity", sa.String(16), nullable=True), sa.Column("normal_review_rate", sa.Numeric(5, 2), server_default="10", nullable=False),
        sa.Column("reviewer_ids", postgresql.JSONB(), server_default="[]", nullable=False), sa.Column("scope_snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("estimate_signature", sa.String(64), nullable=True), sa.Column("estimate_result", postgresql.JSONB(), server_default="{}", nullable=False), sa.Column("estimated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_algorithm_version", sa.String(16), server_default="v1", nullable=False), sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True), sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["scorecard_version_id"], ["quality_scorecard_versions.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["created_by_id"], ["employees.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_plans_tenant_status_updated", "quality_plans", ["tenant_id", "status", "updated_at"])
    op.create_index("ix_quality_plans_tenant_mode_status", "quality_plans", ["tenant_id", "run_mode", "status"])
    op.create_table(
        "quality_plan_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False), sa.Column("plan_id", sa.Integer(), nullable=False), sa.Column("conversation_id", sa.Integer(), nullable=False), sa.Column("target_agent_id", sa.Integer(), nullable=False),
        sa.Column("segment_ids", postgresql.JSONB(), server_default="[]", nullable=False), sa.Column("agent_name_snapshot", sa.String(128), nullable=True), sa.Column("group_id_snapshot", sa.Integer(), nullable=True), sa.Column("group_name_snapshot", sa.String(128), nullable=True),
        sa.Column("conversation_ended_at", sa.DateTime(timezone=True), nullable=False), sa.Column("sampled", sa.Boolean(), server_default=sa.text("true"), nullable=False), sa.Column("sample_value", sa.Numeric(8, 6), nullable=False), sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["quality_plans.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["target_agent_id"], ["employees.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("plan_id", "conversation_id", "target_agent_id", name="uq_quality_plan_candidate_object"),
    )
    op.create_index("ix_quality_plan_candidates_plan_status", "quality_plan_candidates", ["plan_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_quality_plan_candidates_plan_status", table_name="quality_plan_candidates"); op.drop_table("quality_plan_candidates")
    op.drop_index("ix_quality_plans_tenant_mode_status", table_name="quality_plans"); op.drop_index("ix_quality_plans_tenant_status_updated", table_name="quality_plans"); op.drop_table("quality_plans")
