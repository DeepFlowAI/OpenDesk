"""Data access for online quality reviews."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.quality import (
    QualityPlan,
    QualityPlanCandidate,
    QualityHumanReviewDraft,
    QualityReviewAudit,
    QualityReview,
    QualityReviewItem,
    QualityScorecardCriterion,
    QualityScorecardSection,
    QualityScorecardVersion,
)


class QualityReviewRepository:
    @staticmethod
    async def unmaterialized_candidates(db: AsyncSession, tenant_id: int, plan_id: int) -> list[QualityPlanCandidate]:
        result = await db.execute(
            select(QualityPlanCandidate)
            .join(QualityPlan, QualityPlan.id == QualityPlanCandidate.plan_id)
            .outerjoin(QualityReview, QualityReview.candidate_id == QualityPlanCandidate.id)
            .where(QualityPlan.tenant_id == tenant_id, QualityPlan.id == plan_id, QualityPlanCandidate.sampled.is_(True), QualityReview.id.is_(None))
            .options(selectinload(QualityPlanCandidate.plan))
            .order_by(QualityPlanCandidate.id)
            .with_for_update(of=QualityPlanCandidate, skip_locked=True)
        )
        return list(result.scalars().unique().all())

    @staticmethod
    async def scorecard_version(db: AsyncSession, version_id: int) -> QualityScorecardVersion | None:
        result = await db.execute(
            select(QualityScorecardVersion)
            .where(QualityScorecardVersion.id == version_id)
            .options(selectinload(QualityScorecardVersion.sections).selectinload(QualityScorecardSection.criteria).selectinload(QualityScorecardCriterion.options))
        )
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def reviews_by_plan(db: AsyncSession, plan_id: int) -> list[QualityReview]:
        result = await db.execute(
            select(QualityReview)
            .where(QualityReview.plan_id == plan_id)
            .options(selectinload(QualityReview.items))
        )
        return list(result.scalars().unique().all())

    @staticmethod
    async def conversation_snapshot(db: AsyncSession, conversation_id: int) -> tuple[Conversation | None, list[Message]]:
        conversation = await db.get(Conversation, conversation_id)
        messages = list((await db.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at, Message.id))).scalars().all())
        return conversation, messages

    @staticmethod
    async def review_by_call_id(db: AsyncSession, call_id: int) -> tuple[QualityReviewItem, QualityReview] | None:
        result = await db.execute(
            select(QualityReviewItem, QualityReview)
            .join(QualityReview, QualityReview.id == QualityReviewItem.review_id)
            .where(QualityReviewItem.llm_call_id == call_id)
            .options(selectinload(QualityReview.items))
        )
        return result.unique().one_or_none()

    @staticmethod
    async def review_by_id(
        db: AsyncSession, tenant_id: int, review_id: int
    ) -> QualityReview | None:
        result = await db.execute(
            select(QualityReview)
            .where(QualityReview.id == review_id, QualityReview.tenant_id == tenant_id)
            .options(selectinload(QualityReview.items))
        )
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def plan(db: AsyncSession, plan_id: int) -> QualityPlan | None:
        return await db.get(QualityPlan, plan_id)

    @staticmethod
    async def draft(db: AsyncSession, review_id: int) -> QualityHumanReviewDraft | None:
        result = await db.execute(
            select(QualityHumanReviewDraft)
            .where(QualityHumanReviewDraft.review_id == review_id)
            .options(selectinload(QualityHumanReviewDraft.items))
        )
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def pending_mine(
        db: AsyncSession,
        tenant_id: int,
        reviewer_id: int,
        plan_id: int,
        *,
        allowed_agent_ids: list[int] | None,
        page: int,
        per_page: int,
    ) -> tuple[list[QualityReview], int]:
        filters = [
            QualityReview.tenant_id == tenant_id,
            QualityReview.plan_id == plan_id,
            QualityReview.assigned_reviewer_id == reviewer_id,
            QualityReview.status.in_(["pending_human", "human_reviewing"]),
        ]
        if allowed_agent_ids is not None:
            filters.append(QualityReview.target_agent_id.in_(allowed_agent_ids))
        total = await db.scalar(select(func.count()).select_from(QualityReview).where(*filters))
        result = await db.execute(
            select(QualityReview)
            .where(*filters)
            .order_by(QualityReview.created_at.asc(), QualityReview.id.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), int(total or 0)

    @staticmethod
    async def list_reviews(
        db: AsyncSession,
        tenant_id: int,
        plan_id: int,
        *,
        allowed_agent_ids: list[int] | None,
        status: str | None,
        source: str | None,
        agent_id: int | None,
        page: int,
        per_page: int,
    ) -> tuple[list[QualityReview], int]:
        filters = [QualityReview.tenant_id == tenant_id, QualityReview.plan_id == plan_id]
        if allowed_agent_ids is not None:
            filters.append(QualityReview.target_agent_id.in_(allowed_agent_ids))
        if status:
            filters.append(QualityReview.status == status)
        if source:
            if source == "ai_pending":
                filters.extend([
                    QualityReview.final_source.is_(None),
                    QualityReview.ai_outcome.is_not(None),
                ])
            elif source == "none":
                filters.extend([
                    QualityReview.final_source.is_(None),
                    QualityReview.ai_outcome.is_(None),
                ])
            else:
                filters.append(QualityReview.final_source == source)
        if agent_id:
            filters.append(QualityReview.target_agent_id == agent_id)
        total = await db.scalar(select(func.count()).select_from(QualityReview).where(*filters))
        result = await db.execute(
            select(QualityReview)
            .where(*filters)
            .order_by(
                QualityReview.completed_at.desc().nullslast(),
                QualityReview.created_at.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), int(total or 0)

    @staticmethod
    async def audits(db: AsyncSession, review_id: int) -> list[QualityReviewAudit]:
        result = await db.execute(
            select(QualityReviewAudit)
            .where(QualityReviewAudit.review_id == review_id)
            .order_by(QualityReviewAudit.created_at.asc(), QualityReviewAudit.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def reviews_for_statistics(
        db: AsyncSession,
        tenant_id: int,
        plan_id: int,
        *,
        allowed_agent_ids: list[int] | None,
    ) -> list[QualityReview]:
        filters = [
            QualityReview.tenant_id == tenant_id,
            QualityReview.plan_id == plan_id,
        ]
        if allowed_agent_ids is not None:
            filters.append(QualityReview.target_agent_id.in_(allowed_agent_ids))
        result = await db.execute(select(QualityReview).where(*filters))
        return list(result.scalars().all())
