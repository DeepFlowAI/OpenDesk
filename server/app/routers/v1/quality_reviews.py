"""Online quality review workbench and record detail endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_permission
from app.schemas.permission import EffectivePrincipal
from app.schemas.quality_review import (
    QualityDraftPayload,
    QualityReassignPayload,
    QualityReviewDetailResponse,
    QualityReviewListItem,
    QualityUnablePayload,
    QualityWorkbenchResponse,
)
from app.services.quality_review_service import QualityReviewService

router = APIRouter(prefix="/quality/online/reviews", tags=["OnlineQualityReviews"])


@router.get("/{review_id}", response_model=QualityReviewDetailResponse)
async def get_review_detail(
    review_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.record.view")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityReviewDetailResponse:
    return await QualityReviewService.detail(db, principal, review_id)


@router.get("/{review_id}/workbench", response_model=QualityWorkbenchResponse)
async def get_review_workbench(
    review_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.review.perform")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityWorkbenchResponse:
    return await QualityReviewService.get_workbench(db, principal, review_id)


@router.post("/{review_id}/open", response_model=QualityWorkbenchResponse)
async def open_review(
    review_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.review.perform")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityWorkbenchResponse:
    return await QualityReviewService.open_review(db, principal, review_id)


@router.put("/{review_id}/draft", response_model=QualityWorkbenchResponse)
async def save_review_draft(
    review_id: int,
    body: QualityDraftPayload,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.review.perform")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityWorkbenchResponse:
    return await QualityReviewService.save_draft(db, principal, review_id, body)


@router.post("/{review_id}/submit", response_model=QualityReviewDetailResponse)
async def submit_review(
    review_id: int,
    body: QualityDraftPayload,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.review.perform")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityReviewDetailResponse:
    return await QualityReviewService.submit(db, principal, review_id, body)


@router.post("/{review_id}/submit-unable", response_model=QualityReviewDetailResponse)
async def submit_review_unable(
    review_id: int,
    body: QualityUnablePayload,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.review.perform")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityReviewDetailResponse:
    return await QualityReviewService.submit_unable(db, principal, review_id, body)


@router.post("/{review_id}/reassign", response_model=QualityReviewListItem)
async def reassign_review(
    review_id: int,
    body: QualityReassignPayload,
    principal: EffectivePrincipal = Depends(
        require_permission("quality.online.plan.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> QualityReviewListItem:
    return await QualityReviewService.reassign(db, principal, review_id, body)
