"""Online quality review models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class QualityScorecard(Base, TimestampMixin):
    """Tenant-owned online quality scorecard."""

    __tablename__ = "quality_scorecards"
    __table_args__ = (
        Index("ix_quality_scorecards_tenant_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_quality_scorecards_tenant_name", "tenant_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    current_version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list["QualityScorecardVersion"]] = relationship(
        back_populates="scorecard",
        cascade="all, delete-orphan",
        order_by="QualityScorecardVersion.version_number",
        lazy="selectin",
    )


class QualityScorecardVersion(Base, TimestampMixin):
    """Immutable after publication scorecard version."""

    __tablename__ = "quality_scorecard_versions"
    __table_args__ = (
        UniqueConstraint("scorecard_id", "version_number", name="uq_quality_scorecard_version"),
        Index(
            "uq_quality_scorecard_single_draft",
            "scorecard_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scorecard_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quality_scorecards.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    pass_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True, server_default="80")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )

    scorecard: Mapped[QualityScorecard] = relationship(back_populates="versions")
    sections: Mapped[list["QualityScorecardSection"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="QualityScorecardSection.sort_order",
        lazy="selectin",
    )


class QualityScorecardSection(Base):
    """A display group inside a scorecard version."""

    __tablename__ = "quality_scorecard_sections"
    __table_args__ = (
        UniqueConstraint("version_id", "sort_order", name="uq_quality_scorecard_section_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quality_scorecard_versions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    version: Mapped[QualityScorecardVersion] = relationship(back_populates="sections")
    criteria: Mapped[list["QualityScorecardCriterion"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="QualityScorecardCriterion.sort_order",
        lazy="selectin",
    )


class QualityScorecardCriterion(Base):
    """A scored or observational criterion."""

    __tablename__ = "quality_scorecard_criteria"
    __table_args__ = (
        UniqueConstraint("section_id", "sort_order", name="uq_quality_scorecard_criterion_order"),
        Index("ix_quality_scorecard_criteria_stable_key", "stable_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quality_scorecard_sections.id", ondelete="CASCADE"), nullable=False
    )
    stable_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rubric: Mapped[str] = mapped_column(String(2000), nullable=False)
    max_points: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="10")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    evidence_policy: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="issue_only"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    section: Mapped[QualityScorecardSection] = relationship(back_populates="criteria")
    options: Mapped[list["QualityScorecardOption"]] = relationship(
        back_populates="criterion",
        cascade="all, delete-orphan",
        order_by="QualityScorecardOption.sort_order",
        lazy="selectin",
    )


class QualityScorecardOption(Base):
    """A selectable published result for one criterion."""

    __tablename__ = "quality_scorecard_options"
    __table_args__ = (
        UniqueConstraint("criterion_id", "sort_order", name="uq_quality_scorecard_option_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    criterion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quality_scorecard_criteria.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    points: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="normal")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    criterion: Mapped[QualityScorecardCriterion] = relationship(back_populates="options")


class QualityPlan(Base, TimestampMixin):
    """Configuration and execution boundary for online quality reviews."""

    __tablename__ = "quality_plans"
    __table_args__ = (
        Index("ix_quality_plans_tenant_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_quality_plans_tenant_mode_status", "tenant_id", "run_mode", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    run_mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="continuous")
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="draft")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    range_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    range_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    group_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    agent_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    coverage_mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="all")
    sample_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="100")
    scorecard_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("quality_scorecard_versions.id", ondelete="RESTRICT"), nullable=False)
    execution_strategy: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ai")
    manual_route_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    normal_review_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="10")
    reviewer_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    scope_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    estimate_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimate_result: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    estimated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_algorithm_version: Mapped[str] = mapped_column(String(16), nullable=False, server_default="v1")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_candidate_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)

    candidates: Mapped[list["QualityPlanCandidate"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", lazy="selectin"
    )


class QualityPlanCandidate(Base, TimestampMixin):
    """One stable plan candidate: conversation plus target agent."""

    __tablename__ = "quality_plan_candidates"
    __table_args__ = (
        UniqueConstraint("plan_id", "conversation_id", "target_agent_id", name="uq_quality_plan_candidate_object"),
        Index("ix_quality_plan_candidates_plan_status", "plan_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("quality_plans.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False)
    target_agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    segment_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    agent_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    group_id_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    group_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conversation_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sampled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sample_value: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")

    plan: Mapped[QualityPlan] = relationship(back_populates="candidates")


class QualityReview(Base, TimestampMixin):
    """One conversation and target-agent quality evaluation."""

    __tablename__ = "quality_reviews"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_quality_review_candidate"),
        Index("ix_quality_reviews_plan_status", "plan_id", "status"),
        Index("ix_quality_reviews_tenant_agent", "tenant_id", "target_agent_id"),
        Index("ix_quality_reviews_reviewer_status", "assigned_reviewer_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("quality_plans.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[int] = mapped_column(Integer, ForeignKey("quality_plan_candidates.id", ondelete="RESTRICT"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False)
    target_agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    scorecard_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("quality_scorecard_versions.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="ai_processing")
    conversation_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    message_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    route_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    assigned_reviewer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    ai_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    ai_outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    issue_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    final_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    final_outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    final_issue_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    unable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["QualityReviewItem"]] = relationship(back_populates="review", cascade="all, delete-orphan", order_by="QualityReviewItem.sort_order", lazy="selectin")


class QualityReviewItem(Base, TimestampMixin):
    """Per-criterion AI and eventual human result."""

    __tablename__ = "quality_review_items"
    __table_args__ = (
        UniqueConstraint("review_id", "criterion_id", name="uq_quality_review_item_criterion"),
        Index("ix_quality_review_items_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, ForeignKey("quality_reviews.id", ondelete="CASCADE"), nullable=False)
    criterion_id: Mapped[int] = mapped_column(Integer, ForeignKey("quality_scorecard_criteria.id", ondelete="RESTRICT"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    criterion_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    result_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    option_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_message_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    llm_call_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("platform_llm_calls.id", ondelete="SET NULL"), nullable=True)
    execution_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    review: Mapped[QualityReview] = relationship(back_populates="items")


class QualityHumanReviewDraft(Base, TimestampMixin):
    """Mutable human decision set; frozen after submission."""

    __tablename__ = "quality_human_review_drafts"
    __table_args__ = (UniqueConstraint("review_id", name="uq_quality_human_draft_review"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quality_reviews.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    overall_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["QualityHumanReviewItem"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="QualityHumanReviewItem.id",
        lazy="selectin",
    )


class QualityHumanReviewItem(Base, TimestampMixin):
    """Human result kept separately from immutable AI output."""

    __tablename__ = "quality_human_review_items"
    __table_args__ = (
        UniqueConstraint("draft_id", "review_item_id", name="uq_quality_human_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quality_human_review_drafts.id", ondelete="CASCADE"), nullable=False
    )
    review_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quality_review_items.id", ondelete="CASCADE"), nullable=False
    )
    result_type: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="unanswered"
    )
    option_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    judgment: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_message_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    draft: Mapped[QualityHumanReviewDraft] = relationship(back_populates="items")


class QualityReviewAudit(Base):
    """Append-only review mutation audit."""

    __tablename__ = "quality_review_audits"
    __table_args__ = (Index("ix_quality_review_audits_review_created", "review_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quality_reviews.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    before_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    after_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
