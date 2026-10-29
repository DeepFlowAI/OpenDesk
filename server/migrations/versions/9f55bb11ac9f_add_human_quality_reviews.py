"""add human online quality review results

Revision ID: 9f55bb11ac9f
Revises: 8e44aa00fb8e
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "9f55bb11ac9f"
down_revision: Union[str, None] = "8e44aa00fb8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quality_reviews", sa.Column("final_source", sa.String(16), nullable=True))
    op.add_column("quality_reviews", sa.Column("final_score", sa.Numeric(5, 1), nullable=True))
    op.add_column("quality_reviews", sa.Column("final_outcome", sa.String(24), nullable=True))
    op.add_column("quality_reviews", sa.Column("final_issue_count", sa.Integer(), nullable=True))
    op.add_column("quality_reviews", sa.Column("overall_comment", sa.Text(), nullable=True))
    op.add_column("quality_reviews", sa.Column("unable_reason", sa.Text(), nullable=True))
    op.add_column("quality_reviews", sa.Column("submitted_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_quality_reviews_submitted_by", "quality_reviews", "employees", ["submitted_by_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "quality_human_review_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("overall_comment", sa.Text(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["quality_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", name="uq_quality_human_draft_review"),
    )
    op.create_table(
        "quality_human_review_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("review_item_id", sa.Integer(), nullable=False),
        sa.Column("result_type", sa.String(24), server_default="unanswered", nullable=False),
        sa.Column("option_id", sa.Integer(), nullable=True),
        sa.Column("judgment", sa.Text(), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("evidence_message_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["quality_human_review_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_item_id"], ["quality_review_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", "review_item_id", name="uq_quality_human_item"),
    )
    op.create_table(
        "quality_review_audits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("before_snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("after_snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["quality_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_review_audits_review_created", "quality_review_audits", ["review_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_quality_review_audits_review_created", table_name="quality_review_audits")
    op.drop_table("quality_review_audits")
    op.drop_table("quality_human_review_items")
    op.drop_table("quality_human_review_drafts")
    op.drop_constraint("fk_quality_reviews_submitted_by", "quality_reviews", type_="foreignkey")
    op.drop_column("quality_reviews", "submitted_by_id")
    op.drop_column("quality_reviews", "unable_reason")
    op.drop_column("quality_reviews", "overall_comment")
    op.drop_column("quality_reviews", "final_issue_count")
    op.drop_column("quality_reviews", "final_outcome")
    op.drop_column("quality_reviews", "final_score")
    op.drop_column("quality_reviews", "final_source")
