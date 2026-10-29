"""Data access for online quality scorecards."""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.quality import (
    QualityScorecard,
    QualityScorecardCriterion,
    QualityScorecardOption,
    QualityScorecardSection,
    QualityScorecardVersion,
)


def _scorecard_load_options():
    return selectinload(QualityScorecard.versions).selectinload(
        QualityScorecardVersion.sections
    ).selectinload(QualityScorecardSection.criteria).selectinload(
        QualityScorecardCriterion.options
    )


class QualityScorecardRepository:
    """Repository for scorecard aggregates."""

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        tenant_id: int,
        *,
        q: str | None,
        status: str | None,
        page: int,
        per_page: int,
    ) -> tuple[list[QualityScorecard], int]:
        filters = [QualityScorecard.tenant_id == tenant_id]
        if q:
            filters.append(QualityScorecard.name.ilike(f"%{q}%"))
        if status:
            filters.append(QualityScorecard.status == status)
        total_result = await db.execute(
            select(func.count()).select_from(QualityScorecard).where(*filters)
        )
        result = await db.execute(
            select(QualityScorecard)
            .where(*filters)
            .options(_scorecard_load_options())
            .order_by(QualityScorecard.updated_at.desc(), QualityScorecard.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().unique().all()), int(total_result.scalar_one())

    @staticmethod
    async def get_by_id(
        db: AsyncSession, tenant_id: int, scorecard_id: int
    ) -> QualityScorecard | None:
        result = await db.execute(
            select(QualityScorecard)
            .where(
                QualityScorecard.id == scorecard_id,
                QualityScorecard.tenant_id == tenant_id,
            )
            .options(_scorecard_load_options())
        )
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def save(db: AsyncSession, scorecard: QualityScorecard) -> QualityScorecard:
        db.add(scorecard)
        await db.commit()
        # onupdate=func.now() expires updated_at after flush/commit. Reloading
        # with selectinload avoids MissingGreenlet during response serialization.
        reloaded = await QualityScorecardRepository.get_by_id(
            db, scorecard.tenant_id, scorecard.id
        )
        assert reloaded is not None
        return reloaded

    @staticmethod
    async def flush(db: AsyncSession) -> None:
        await db.flush()


def build_sections(
    inputs: list,
) -> list[QualityScorecardSection]:
    """Build an ORM section tree from validated input schemas."""
    sections: list[QualityScorecardSection] = []
    for section_order, section_input in enumerate(inputs):
        section = QualityScorecardSection(
            name=section_input.name,
            sort_order=section_order,
            criteria=[],
        )
        for criterion_order, criterion_input in enumerate(section_input.criteria):
            criterion = QualityScorecardCriterion(
                stable_key=criterion_input.stable_key or uuid4(),
                name=criterion_input.name,
                rubric=criterion_input.rubric,
                max_points=criterion_input.max_points,
                is_required=criterion_input.is_required,
                evidence_policy=criterion_input.evidence_policy,
                sort_order=criterion_order,
                options=[],
            )
            for option_order, option_input in enumerate(criterion_input.options):
                criterion.options.append(
                    QualityScorecardOption(
                        name=option_input.name,
                        description=option_input.description,
                        points=option_input.points,
                        severity=option_input.severity,
                        sort_order=option_order,
                    )
                )
            section.criteria.append(criterion)
        sections.append(section)
    return sections
