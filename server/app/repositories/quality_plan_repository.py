"""Data access for online quality plans and candidates."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.conversation_reception_segment import ConversationReceptionSegment
from app.models.quality import QualityPlan, QualityPlanCandidate, QualityScorecard, QualityScorecardVersion


class QualityPlanRepository:
    @staticmethod
    async def list_paginated(db: AsyncSession, tenant_id: int, *, q: str | None, status: str | None, run_mode: str | None, page: int, per_page: int) -> tuple[list[QualityPlan], int]:
        filters = [QualityPlan.tenant_id == tenant_id]
        if q:
            filters.append(QualityPlan.name.ilike(f"%{q}%"))
        if status:
            filters.append(QualityPlan.status == status)
        if run_mode:
            filters.append(QualityPlan.run_mode == run_mode)
        total = await db.scalar(select(func.count()).select_from(QualityPlan).where(*filters))
        result = await db.execute(select(QualityPlan).where(*filters).order_by(QualityPlan.updated_at.desc()).offset((page - 1) * per_page).limit(per_page))
        return list(result.scalars().all()), int(total or 0)

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, plan_id: int) -> QualityPlan | None:
        result = await db.execute(select(QualityPlan).where(QualityPlan.id == plan_id, QualityPlan.tenant_id == tenant_id).options(selectinload(QualityPlan.candidates)))
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def get_published_version(db: AsyncSession, tenant_id: int, version_id: int) -> QualityScorecardVersion | None:
        result = await db.execute(
            select(QualityScorecardVersion)
            .join(QualityScorecard, QualityScorecard.id == QualityScorecardVersion.scorecard_id)
            .where(
                QualityScorecardVersion.id == version_id,
                QualityScorecardVersion.status == "published",
                QualityScorecard.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def candidate_segments(db: AsyncSession, tenant_id: int, *, start_at: datetime, end_at: datetime, group_ids: list[int], agent_ids: list[int], scope: str, scope_group_ids: list[int], limit: int = 10001) -> list[tuple[ConversationReceptionSegment, Conversation]]:
        filters = [
            ConversationReceptionSegment.tenant_id == tenant_id,
            ConversationReceptionSegment.agent_id.is_not(None),
            ConversationReceptionSegment.agent_message_count > 0,
            Conversation.ended_at.is_not(None),
            Conversation.ended_at >= start_at,
            Conversation.ended_at < end_at,
        ]
        if group_ids:
            filters.append(ConversationReceptionSegment.group_id.in_(group_ids))
        if agent_ids:
            filters.append(ConversationReceptionSegment.agent_id.in_(agent_ids))
        if scope == "group":
            filters.append(ConversationReceptionSegment.group_id.in_(scope_group_ids))
        if scope == "self":
            if not agent_ids:
                return []
            filters.append(ConversationReceptionSegment.agent_id.in_(agent_ids))
        result = await db.execute(
            select(ConversationReceptionSegment, Conversation)
            .join(Conversation, Conversation.id == ConversationReceptionSegment.conversation_id)
            .where(*filters)
            .order_by(Conversation.ended_at.asc())
            .limit(limit * 4)
        )
        return list(result.all())

    @staticmethod
    async def running_continuous(db: AsyncSession) -> list[QualityPlan]:
        result = await db.execute(
            select(QualityPlan).where(
                QualityPlan.run_mode == "continuous",
                QualityPlan.status == "running",
                QualityPlan.activated_at.is_not(None),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def insert_candidates_ignore(
        db: AsyncSession, values: list[dict]
    ) -> int:
        if not values:
            return 0
        statement = (
            insert(QualityPlanCandidate)
            .values(values)
            .on_conflict_do_nothing(
                index_elements=["plan_id", "conversation_id", "target_agent_id"]
            )
        )
        result = await db.execute(statement)
        await db.commit()
        return int(result.rowcount or 0)

    @staticmethod
    async def save(db: AsyncSession, plan: QualityPlan) -> QualityPlan:
        db.add(plan)
        await db.commit()
        return await QualityPlanRepository._reload(db, plan)

    @staticmethod
    async def replace_candidates(
        db: AsyncSession, plan: QualityPlan, candidates: list[QualityPlanCandidate]
    ) -> QualityPlan:
        plan.candidates.clear()
        await db.flush()
        plan.candidates = candidates
        await db.commit()
        return await QualityPlanRepository._reload(db, plan)

    @staticmethod
    async def _reload(db: AsyncSession, plan: QualityPlan) -> QualityPlan:
        # onupdate=func.now() expires updated_at after flush/commit. Reloading
        # avoids MissingGreenlet during response serialization.
        reloaded = await QualityPlanRepository.get_by_id(db, plan.tenant_id, plan.id)
        assert reloaded is not None
        return reloaded
