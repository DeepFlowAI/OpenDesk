"""
Learning center employee-side router: my courses, course detail, material
playback and progress.

All endpoints require the ``learning.center.use`` permission.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import EffectivePrincipal, get_db, require_permission
from app.schemas.learning import (
    CompleteMaterialResponse,
    LearningRecordResponse,
    MaterialOpenResponse,
    MyCourseDetail,
    MyCourseListResponse,
    ProgressReportRequest,
)
from app.services.learning_my_service import LearningMyService

router = APIRouter(prefix="/learning/my", tags=["Learning My"])

UseDep = Depends(require_permission("learning.center.use"))


@router.get("/courses", response_model=MyCourseListResponse)
async def list_my_courses(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> MyCourseListResponse:
    """List published courses visible to the current employee, with my progress."""
    return await LearningMyService.list_my_courses(
        db, tenant_id=principal.tenant_id, employee_id=principal.user_id, q=q, page=page, per_page=per_page
    )


@router.get("/courses/{course_id}", response_model=MyCourseDetail)
async def get_my_course_detail(
    course_id: int,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> MyCourseDetail:
    """Course learning page: section/material tree with my per-material progress."""
    return await LearningMyService.get_my_course_detail(
        db, tenant_id=principal.tenant_id, course_id=course_id, employee_id=principal.user_id
    )


@router.post("/materials/{material_id}/open", response_model=MaterialOpenResponse)
async def open_material(
    material_id: int,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> MaterialOpenResponse:
    """Open a material: upsert the learning record and return playback URLs."""
    return await LearningMyService.open_material(
        db, tenant_id=principal.tenant_id, material_id=material_id, employee_id=principal.user_id
    )


@router.put("/materials/{material_id}/progress", response_model=LearningRecordResponse)
async def report_progress(
    material_id: int,
    body: ProgressReportRequest,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> LearningRecordResponse:
    """Report the playback position (kept as a running max server-side)."""
    return await LearningMyService.report_progress(
        db,
        tenant_id=principal.tenant_id,
        material_id=material_id,
        employee_id=principal.user_id,
        position_seconds=body.position_seconds,
    )


@router.post("/materials/{material_id}/complete", response_model=CompleteMaterialResponse)
async def complete_material(
    material_id: int,
    principal: EffectivePrincipal = UseDep,
    db: AsyncSession = Depends(get_db),
) -> CompleteMaterialResponse:
    """Confirm completion (audio/video require >= 90% played; PDF is unconditional)."""
    return await LearningMyService.complete_material(
        db, tenant_id=principal.tenant_id, material_id=material_id, employee_id=principal.user_id
    )
