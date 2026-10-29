"""add platform llm queue and online quality reviews

Revision ID: 8e44aa00fb8e
Revises: 7d33ff99ea7d
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "8e44aa00fb8e"
down_revision: Union[str, None] = "7d33ff99ea7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_llm_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("business_type", sa.String(48), nullable=False),
        sa.Column("business_id", sa.String(96), nullable=False),
        sa.Column("idempotency_key", sa.String(192), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("execution_round", sa.Integer(), server_default="1", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(128), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_platform_llm_calls_idempotency", "platform_llm_calls", ["idempotency_key"], unique=True)
    op.create_index("ix_platform_llm_calls_dispatch", "platform_llm_calls", ["status", "available_at", "created_at"])
    op.create_index("ix_platform_llm_calls_business", "platform_llm_calls", ["business_type", "business_id"])

    op.create_table(
        "quality_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("target_agent_id", sa.Integer(), nullable=False),
        sa.Column("scorecard_version_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), server_default="ai_processing", nullable=False),
        sa.Column("conversation_snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("message_snapshot", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("route_reasons", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("assigned_reviewer_id", sa.Integer(), nullable=True),
        sa.Column("ai_score", sa.Numeric(5, 1), nullable=True),
        sa.Column("ai_outcome", sa.String(24), nullable=True),
        sa.Column("issue_count", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["quality_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["quality_plan_candidates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_agent_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scorecard_version_id"], ["quality_scorecard_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_reviewer_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", name="uq_quality_review_candidate"),
    )
    op.create_index("ix_quality_reviews_plan_status", "quality_reviews", ["plan_id", "status"])
    op.create_index("ix_quality_reviews_tenant_agent", "quality_reviews", ["tenant_id", "target_agent_id"])
    op.create_index("ix_quality_reviews_reviewer_status", "quality_reviews", ["assigned_reviewer_id", "status"])

    op.create_table(
        "quality_review_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("criterion_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("criterion_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("result_type", sa.String(32), nullable=True),
        sa.Column("option_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_message_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("llm_call_id", sa.BigInteger(), nullable=True),
        sa.Column("execution_round", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["quality_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["criterion_id"], ["quality_scorecard_criteria.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["llm_call_id"], ["platform_llm_calls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "criterion_id", name="uq_quality_review_item_criterion"),
    )
    op.create_index("ix_quality_review_items_status", "quality_review_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_quality_review_items_status", table_name="quality_review_items")
    op.drop_table("quality_review_items")
    op.drop_index("ix_quality_reviews_reviewer_status", table_name="quality_reviews")
    op.drop_index("ix_quality_reviews_tenant_agent", table_name="quality_reviews")
    op.drop_index("ix_quality_reviews_plan_status", table_name="quality_reviews")
    op.drop_table("quality_reviews")
    op.drop_index("ix_platform_llm_calls_business", table_name="platform_llm_calls")
    op.drop_index("ix_platform_llm_calls_dispatch", table_name="platform_llm_calls")
    op.drop_index("uq_platform_llm_calls_idempotency", table_name="platform_llm_calls")
    op.drop_table("platform_llm_calls")
