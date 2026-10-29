"""Online quality plan endpoints."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_permission
from app.schemas.permission import EffectivePrincipal
from app.schemas.quality_plan import QualityPlanEstimateResponse, QualityPlanListResponse, QualityPlanPayload, QualityPlanResponse, QualityPlanReviewersPayload
from app.schemas.quality_review import (
    QualityMaterializeResponse,
    QualityRetryResponse,
    QualityReviewListResponse,
    QualityStatisticsResponse,
)
from app.services.quality_plan_service import QualityPlanService
from app.services.quality_review_execution_service import QualityReviewExecutionService
from app.services.quality_review_service import QualityReviewService

router = APIRouter(prefix="/quality/online/plans", tags=["OnlineQualityPlans"])


@router.get("", response_model=QualityPlanListResponse)
async def list_plans(q: str | None = None, status_filter: str | None = Query(None, alias="status"), run_mode: str | None = None, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100), principal: EffectivePrincipal = Depends(require_permission("quality.online.plan.view")), db: AsyncSession = Depends(get_db)) -> QualityPlanListResponse:
    return await QualityPlanService.list_plans(db, principal, q=q, status=status_filter, run_mode=run_mode, page=page, per_page=per_page)


@router.post("", response_model=QualityPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(body: QualityPlanPayload, principal: EffectivePrincipal = Depends(require_permission("quality.online.plan.manage")), db: AsyncSession = Depends(get_db)) -> QualityPlanResponse:
    return await QualityPlanService.create_plan(db, principal, body)


@router.get("/{plan_id}", response_model=QualityPlanResponse)
async def get_plan(plan_id: int, principal: EffectivePrincipal = Depends(require_permission("quality.online.plan.view")), db: AsyncSession = Depends(get_db)) -> QualityPlanResponse:
    return await QualityPlanService.get_plan(db, principal, plan_id)


@router.put("/{plan_id}", response_model=QualityPlanResponse)
async def update_plan(plan_id: int, body: QualityPlanPayload, principal: EffectivePrincipal = Depends(require_permission("quality.online.plan.manage")), db: AsyncSession = Depends(get_db)) -> QualityPlanResponse:
    return await QualityPlanService.update_plan(db, principal, plan_id, body)


@router.post("/{plan_id}/estimate", response_model=QualityPlanEstimateResponse)
async def estimate_plan(plan_id: int, principal: EffectivePrincipal = Depends(require_permission("quality.online.plan.manage")), db: AsyncSession = Depends(get_db)) -> QualityPlanEstimateResponse:
    return await QualityPlanService.estimate(db, principal, plan_id)


@router.post("/{plan_id}/activate", response_model=QualityPlanResponse)
async def activate_plan(plan_id: int, principal: EffectivePrincipal = Depends(require_permission("quality.online.plan.manage")), db: AsyncSession = Depends(get_db)) -> QualityPlanResponse:
    result = await QualityPlanService.activate(db, principal, plan_id)
    await QualityReviewExecutionService.materialize(db, principal, plan_id)
    return await QualityPlanService.get_plan(db, principal, result.id)


@router.post("/{plan_id}/materialize", response_model=QualityMaterializeResponse)
async def materialize_plan_reviews(
    plan_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.plan.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityMaterializeResponse:
    return await QualityReviewExecutionService.materialize(db, principal, plan_id)


@router.post(
    "/{plan_id}/reviews/{review_id}/retry",
    response_model=QualityRetryResponse,
)
async def retry_failed_review(
    plan_id: int,
    review_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.plan.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityRetryResponse:
    return await QualityReviewExecutionService.retry_failed(
        db, principal, plan_id, review_id
    )


@router.put("/{plan_id}/reviewers", response_model=QualityPlanResponse)
async def update_plan_reviewers(
    plan_id: int,
    body: QualityPlanReviewersPayload,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.plan.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityPlanResponse:
    return await QualityPlanService.update_reviewers(db, principal, plan_id, body)


@router.get("/{plan_id}/pending-mine", response_model=QualityReviewListResponse)
async def list_my_pending_reviews(
    plan_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.review.perform")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityReviewListResponse:
    return await QualityReviewService.pending_mine(
        db, principal, plan_id, page=page, per_page=per_page
    )


@router.get("/{plan_id}/reviews", response_model=QualityReviewListResponse)
async def list_plan_reviews(
    plan_id: int,
    status_filter: str | None = Query(None, alias="status"),
    source: str | None = None,
    agent_id: int | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.record.view")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityReviewListResponse:
    return await QualityReviewService.list_reviews(
        db,
        principal,
        plan_id,
        status=status_filter,
        source=source,
        agent_id=agent_id,
        page=page,
        per_page=per_page,
    )


@router.get("/{plan_id}/statistics", response_model=QualityStatisticsResponse)
async def get_plan_statistics(
    plan_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.record.view")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityStatisticsResponse:
    return await QualityReviewService.statistics(db, principal, plan_id)


@router.post("/{plan_id}/{action}", response_model=QualityPlanResponse)
async def transition_plan(plan_id: int, action: str, principal: EffectivePrincipal = Depends(require_permission("quality.online.plan.manage")), db: AsyncSession = Depends(get_db)) -> QualityPlanResponse:
    if action not in {"pause", "resume"}:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Plan action not found")
    return await QualityPlanService.transition(db, principal, plan_id, action)
