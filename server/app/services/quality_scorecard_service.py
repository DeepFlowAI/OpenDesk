"""Business logic for online quality scorecards."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.quality import QualityScorecard, QualityScorecardVersion
from app.repositories.quality_scorecard_repository import (
    QualityScorecardRepository,
    build_sections,
)
from app.schemas.permission import EffectivePrincipal
from app.schemas.quality_scorecard import (
    QualityScorecardCreate,
    QualityScorecardCriterionInput,
    QualityScorecardListItem,
    QualityScorecardListResponse,
    QualityScorecardResponse,
    QualityScorecardSectionInput,
    QualityScorecardUpdate,
)

_SEVERITY_RANK = {"normal": 0, "notice": 1, "issue": 2, "serious": 3, "fatal": 4}


class QualityScorecardService:
    """Manage scorecard drafts and immutable published versions."""

    @staticmethod
    async def list_scorecards(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        q: str | None,
        status: str | None,
        page: int,
        per_page: int,
    ) -> QualityScorecardListResponse:
        rows, total = await QualityScorecardRepository.list_paginated(
            db,
            principal.tenant_id,
            q=q.strip() if q else None,
            status=status,
            page=page,
            per_page=per_page,
        )
        items = [QualityScorecardService._list_item(row) for row in rows]
        return QualityScorecardListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page,
        )

    @staticmethod
    async def get_scorecard(
        db: AsyncSession, principal: EffectivePrincipal, scorecard_id: int
    ) -> QualityScorecardResponse:
        row = await QualityScorecardService._require_scorecard(
            db, principal.tenant_id, scorecard_id
        )
        return QualityScorecardResponse.model_validate(row)

    @staticmethod
    async def create_scorecard(
        db: AsyncSession,
        principal: EffectivePrincipal,
        body: QualityScorecardCreate,
    ) -> QualityScorecardResponse:
        version = QualityScorecardVersion(
            version_number=1,
            status="draft",
            pass_score=body.pass_score,
        )
        version.sections = build_sections(
            body.sections
            if body.sections is not None
            else [QualityScorecardSectionInput(name="服务规范", criteria=[])]
        )
        row = QualityScorecard(
            tenant_id=principal.tenant_id,
            name=body.name,
            description=body.description,
            status="draft",
            current_version_number=1,
            created_by_id=principal.user_id,
            versions=[version],
        )
        row = await QualityScorecardRepository.save(db, row)
        return QualityScorecardResponse.model_validate(row)

    @staticmethod
    async def update_scorecard(
        db: AsyncSession,
        principal: EffectivePrincipal,
        scorecard_id: int,
        body: QualityScorecardUpdate,
    ) -> QualityScorecardResponse:
        row = await QualityScorecardService._require_scorecard(
            db, principal.tenant_id, scorecard_id
        )
        draft = QualityScorecardService._draft(row)
        if draft is None:
            raise ConflictError("Published scorecard versions are immutable")
        if body.name is not None:
            row.name = body.name.strip()
        if "description" in body.model_fields_set:
            row.description = body.description.strip() if body.description else None
        if "pass_score" in body.model_fields_set:
            draft.pass_score = body.pass_score
        if body.sections is not None:
            draft.sections.clear()
            await QualityScorecardRepository.flush(db)
            draft.sections = build_sections(body.sections)
        row.current_version_number = draft.version_number
        row.status = "draft"
        row = await QualityScorecardRepository.save(db, row)
        return QualityScorecardResponse.model_validate(row)

    @staticmethod
    async def publish_scorecard(
        db: AsyncSession,
        principal: EffectivePrincipal,
        scorecard_id: int,
    ) -> QualityScorecardResponse:
        row = await QualityScorecardService._require_scorecard(
            db, principal.tenant_id, scorecard_id
        )
        draft = QualityScorecardService._draft(row)
        if draft is None:
            raise ConflictError("No draft version is available")
        QualityScorecardService.validate_for_publish(draft.sections, draft.pass_score)
        draft.status = "published"
        draft.published_at = datetime.now(timezone.utc)
        draft.published_by_id = principal.user_id
        row.status = "published"
        row.current_version_number = draft.version_number
        row = await QualityScorecardRepository.save(db, row)
        return QualityScorecardResponse.model_validate(row)

    @staticmethod
    async def create_version(
        db: AsyncSession,
        principal: EffectivePrincipal,
        scorecard_id: int,
    ) -> QualityScorecardResponse:
        row = await QualityScorecardService._require_scorecard(
            db, principal.tenant_id, scorecard_id
        )
        if QualityScorecardService._draft(row) is not None:
            raise ConflictError("A draft version already exists")
        source = max(
            (version for version in row.versions if version.status in {"published", "disabled"}),
            key=lambda version: version.version_number,
            default=None,
        )
        if source is None:
            raise ConflictError("Publish the first version before creating another version")
        copied_sections = [
            QualityScorecardSectionInput(
                name=section.name,
                criteria=[
                    QualityScorecardCriterionInput(
                        stable_key=criterion.stable_key,
                        name=criterion.name,
                        rubric=criterion.rubric,
                        max_points=criterion.max_points,
                        is_required=criterion.is_required,
                        evidence_policy=criterion.evidence_policy,
                        options=[
                            {
                                "name": option.name,
                                "description": option.description,
                                "points": option.points,
                                "severity": option.severity,
                            }
                            for option in criterion.options
                        ],
                    )
                    for criterion in section.criteria
                ],
            )
            for section in source.sections
        ]
        new_version = QualityScorecardVersion(
            version_number=max(version.version_number for version in row.versions) + 1,
            status="draft",
            pass_score=source.pass_score,
            sections=build_sections(copied_sections),
        )
        row.versions.append(new_version)
        row.status = "draft"
        row.current_version_number = new_version.version_number
        row = await QualityScorecardRepository.save(db, row)
        return QualityScorecardResponse.model_validate(row)

    @staticmethod
    async def disable_version(
        db: AsyncSession,
        principal: EffectivePrincipal,
        scorecard_id: int,
        version_number: int,
    ) -> QualityScorecardResponse:
        row = await QualityScorecardService._require_scorecard(
            db, principal.tenant_id, scorecard_id
        )
        version = next(
            (item for item in row.versions if item.version_number == version_number), None
        )
        if version is None:
            raise NotFoundError("Scorecard version not found")
        if version.status != "published":
            raise ConflictError("Only a published version can be disabled")
        version.status = "disabled"
        if version.version_number == row.current_version_number:
            row.status = "disabled"
        row = await QualityScorecardRepository.save(db, row)
        return QualityScorecardResponse.model_validate(row)

    @staticmethod
    def validate_for_publish(
        sections: list,
        pass_score: Decimal | None,
    ) -> None:
        if not sections:
            raise ValidationError("Add at least one criterion")
        for section in sections:
            if not section.name.strip():
                raise ValidationError("Section name is required")
        criteria = [criterion for section in sections for criterion in section.criteria]
        if not criteria:
            raise ValidationError("Add at least one criterion")
        has_scored = any(Decimal(criterion.max_points) > 0 for criterion in criteria)
        if has_scored and pass_score is None:
            raise ValidationError("Pass score is required when scored criteria exist")
        for criterion in criteria:
            QualityScorecardService._validate_criterion(criterion)

    @staticmethod
    def _validate_criterion(criterion) -> None:
        if not criterion.name.strip():
            raise ValidationError("Criterion name is required")
        if len(criterion.rubric.strip()) < 10:
            raise ValidationError(
                "Criterion rubric must contain at least 10 characters",
                details={"criterion": criterion.name},
            )
        max_points = Decimal(criterion.max_points)
        if len(criterion.options) < 2 or len(criterion.options) > 5:
            raise ValidationError(
                "Each criterion must contain between 2 and 5 options",
                details={"criterion": criterion.name},
            )
        if not any(option.severity == "normal" for option in criterion.options):
            raise ValidationError(
                "Each criterion must contain a normal option",
                details={"criterion": criterion.name},
            )
        for option in criterion.options:
            if not option.name.strip() or not option.description.strip():
                raise ValidationError(
                    "Complete the criterion option names and descriptions",
                    details={"criterion": criterion.name},
                )
            points = Decimal(option.points)
            if max_points == 0 and points != 0:
                raise ValidationError(
                    "Observation criterion options must have zero points",
                    details={"criterion": criterion.name, "option": option.name},
                )
            if points < 0 or points > max_points:
                raise ValidationError(
                    "Option points must be between 0 and the criterion maximum",
                    details={"criterion": criterion.name, "option": option.name},
                )
            if option.severity not in _SEVERITY_RANK:
                raise ValidationError("Unsupported severity")
        if any(option.severity == "fatal" for option in criterion.options):
            if criterion.evidence_policy == "none":
                raise ValidationError(
                    "Fatal criteria must require evidence",
                    details={"criterion": criterion.name},
                )

    @staticmethod
    async def _require_scorecard(
        db: AsyncSession, tenant_id: int, scorecard_id: int
    ) -> QualityScorecard:
        row = await QualityScorecardRepository.get_by_id(db, tenant_id, scorecard_id)
        if row is None:
            raise NotFoundError("Scorecard not found")
        return row

    @staticmethod
    def _draft(row: QualityScorecard) -> QualityScorecardVersion | None:
        return next((version for version in row.versions if version.status == "draft"), None)

    @staticmethod
    def _list_item(row: QualityScorecard) -> QualityScorecardListItem:
        current = next(
            (
                version
                for version in row.versions
                if version.version_number == row.current_version_number
            ),
            row.versions[-1],
        )
        criteria = [criterion for section in current.sections for criterion in section.criteria]
        scored_count = sum(Decimal(criterion.max_points) > 0 for criterion in criteria)
        return QualityScorecardListItem(
            id=row.id,
            name=row.name,
            description=row.description,
            status=row.status,
            current_version_number=row.current_version_number,
            current_version_id=current.id,
            criterion_count=len(criteria),
            scored_count=scored_count,
            observation_count=len(criteria) - scored_count,
            pass_score=current.pass_score,
            updated_at=row.updated_at,
        )
