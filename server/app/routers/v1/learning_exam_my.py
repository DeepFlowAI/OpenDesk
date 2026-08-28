"""
Learning center employee-side exam router: my exams, attempt lifecycle
(start/take/submit/abandon) and result review.

All endpoints require the ``learning.center.use`` permission.
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import EffectivePrincipal, get_db, require_permission
from app.schemas.learning import MessageResponse
from app.schemas.learning_exam import (
    AttemptDetailResponse,
    AttemptStartResponse,
    AttemptSubmitRequest,
    AttemptSubmitResponse,
    MyExamListResponse,
    MyExamSummary,
)
from app.services.learning_exam_my_service import LearningExamMyService

router = APIRouter(prefix="/learning/my", tags=["Learning My Exams"])

UseDep = Depends(require_permission("learning.center.use"))


@router.get("/exams", response_model=MyExamListResponse)
async def list_my_exams(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> MyExamListResponse:
    """List published exams visible to the current employee, with my best score."""
    return await LearningExamMyService.list_my_exams(
        db, tenant_id=principal.tenant_id, employee_id=principal.user_id, q=q, page=page, per_page=per_page
    )


@router.get("/exams/{exam_id}", response_model=MyExamSummary)
async def get_my_exam_summary(
    exam_id: int,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> MyExamSummary:
    """Exam rules + my best score + submitted attempt history."""
    return await LearningExamMyService.get_my_exam_summary(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, employee_id=principal.user_id
    )


@router.post(
    "/exams/{exam_id}/attempts",
    response_model=AttemptStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_attempt(
    exam_id: int,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> AttemptStartResponse:
    """Start an attempt: snapshot the questions (optionally shuffled)."""
    return await LearningExamMyService.start_attempt(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, employee_id=principal.user_id
    )


@router.get("/exam-attempts/{attempt_id}", response_model=AttemptDetailResponse)
async def get_attempt(
    attempt_id: int,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> AttemptDetailResponse:
    """Taking state (answers hidden) or per-question review (submitted)."""
    return await LearningExamMyService.get_attempt_detail(
        db, tenant_id=principal.tenant_id, attempt_id=attempt_id, employee_id=principal.user_id
    )


@router.post("/exam-attempts/{attempt_id}/submit", response_model=AttemptSubmitResponse)
async def submit_attempt(
    attempt_id: int,
    body: AttemptSubmitRequest,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> AttemptSubmitResponse:
    """Submit and auto-grade the attempt."""
    return await LearningExamMyService.submit_attempt(
        db, tenant_id=principal.tenant_id, attempt_id=attempt_id, employee_id=principal.user_id,
        answers=body.answers,
    )


@router.post("/exam-attempts/{attempt_id}/abandon", response_model=MessageResponse)
async def abandon_attempt(
    attempt_id: int,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Abandon an in-progress attempt (leaving without submitting costs nothing)."""
    await LearningExamMyService.abandon_attempt(
        db, tenant_id=principal.tenant_id, attempt_id=attempt_id, employee_id=principal.user_id
    )
    return MessageResponse(message="Abandoned successfully")
