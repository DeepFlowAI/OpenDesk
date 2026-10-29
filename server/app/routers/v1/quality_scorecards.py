"""Online quality scorecard endpoints."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_permission
from app.schemas.permission import EffectivePrincipal
from app.schemas.quality_scorecard import (
    QualityScorecardCreate,
    QualityScorecardListResponse,
    QualityScorecardResponse,
    QualityScorecardUpdate,
)
from app.services.quality_scorecard_service import QualityScorecardService

router = APIRouter(prefix="/quality/online/scorecards", tags=["OnlineQualityScorecards"])


@router.get("", response_model=QualityScorecardListResponse)
async def list_scorecards(
    q: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.scorecard.view")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityScorecardListResponse:
    return await QualityScorecardService.list_scorecards(
        db,
        principal,
        q=q,
        status=status_filter,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=QualityScorecardResponse, status_code=status.HTTP_201_CREATED)
async def create_scorecard(
    body: QualityScorecardCreate,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.scorecard.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityScorecardResponse:
    return await QualityScorecardService.create_scorecard(db, principal, body)


@router.get("/{scorecard_id}", response_model=QualityScorecardResponse)
async def get_scorecard(
    scorecard_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.scorecard.view")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityScorecardResponse:
    return await QualityScorecardService.get_scorecard(db, principal, scorecard_id)


@router.patch("/{scorecard_id}", response_model=QualityScorecardResponse)
async def update_scorecard(
    scorecard_id: int,
    body: QualityScorecardUpdate,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.scorecard.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityScorecardResponse:
    return await QualityScorecardService.update_scorecard(
        db, principal, scorecard_id, body
    )


@router.post("/{scorecard_id}/publish", response_model=QualityScorecardResponse)
async def publish_scorecard(
    scorecard_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.scorecard.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityScorecardResponse:
    return await QualityScorecardService.publish_scorecard(db, principal, scorecard_id)


@router.post("/{scorecard_id}/versions", response_model=QualityScorecardResponse)
async def create_scorecard_version(
    scorecard_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.scorecard.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityScorecardResponse:
    return await QualityScorecardService.create_version(db, principal, scorecard_id)


@router.post(
    "/{scorecard_id}/versions/{version_number}/disable",
    response_model=QualityScorecardResponse,
)
async def disable_scorecard_version(
    scorecard_id: int,
    version_number: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.scorecard.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityScorecardResponse:
    return await QualityScorecardService.disable_version(
        db, principal, scorecard_id, version_number
    )
