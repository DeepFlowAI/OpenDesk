"""
Learning center admin router: course/section/material management for tenants.

All endpoints require the ``learning.course.manage`` permission.
"""
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import EffectivePrincipal, get_db, require_permission
from app.schemas.learning import (
    AdminCourseListResponse,
    AssignableEmployeeListResponse,
    AssignableGroupListResponse,
    AssignmentAddRequest,
    AssignmentAddResponse,
    AssignmentListResponse,
    CoverUploadResponse,
    LearnerListResponse,
    LearningCourseCreate,
    LearningCourseDetail,
    LearningCourseResponse,
    LearningCourseUpdate,
    LearningCourseVisibilityUpdate,
    LearningMaterialCreate,
    LearningMaterialResponse,
    LearningMaterialUpdate,
    LearningSectionCreate,
    LearningSectionResponse,
    LearningSectionUpdate,
    MaterialOrderUpdate,
    MaterialUploadCredentialRequest,
    MaterialUploadCredentialResponse,
    MessageResponse,
    SectionOrderUpdate,
)
from app.services.learning_admin_service import (
    LearningCourseAdminService,
    LearningMaterialAdminService,
    LearningSectionAdminService,
)
from app.services.learning_assignment_service import LearningAssignmentService

router = APIRouter(prefix="/learning/admin", tags=["Learning Admin"])

ManageDep = Depends(require_permission("learning.course.manage"))


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


@router.get("/courses", response_model=AdminCourseListResponse)
async def list_courses(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AdminCourseListResponse:
    """List courses with stats for the admin table."""
    return await LearningCourseAdminService.list_courses(
        db, tenant_id=principal.tenant_id, page=page, per_page=per_page, q=q, status=status
    )


@router.post("/courses", response_model=LearningCourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: LearningCourseCreate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningCourseResponse:
    """Create a course (starts as draft)."""
    return await LearningCourseAdminService.create_course(
        db, tenant_id=principal.tenant_id, employee_id=principal.user_id, data=body
    )


@router.get("/courses/{course_id}", response_model=LearningCourseDetail)
async def get_course(
    course_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningCourseDetail:
    """Course detail with the section/material tree for the edit page."""
    return await LearningCourseAdminService.get_course_detail(
        db, tenant_id=principal.tenant_id, course_id=course_id
    )


@router.put("/courses/{course_id}", response_model=LearningCourseResponse)
async def update_course(
    course_id: int,
    body: LearningCourseUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningCourseResponse:
    """Update basic info (name / cover / intro)."""
    return await LearningCourseAdminService.update_course(
        db, tenant_id=principal.tenant_id, course_id=course_id, data=body
    )


@router.post("/courses/{course_id}/publish", response_model=LearningCourseResponse)
async def publish_course(
    course_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningCourseResponse:
    """Publish a course (requires at least one section and one material)."""
    return await LearningCourseAdminService.publish_course(db, tenant_id=principal.tenant_id, course_id=course_id)


@router.post("/courses/{course_id}/unpublish", response_model=LearningCourseResponse)
async def unpublish_course(
    course_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningCourseResponse:
    """Unpublish a course; learning records are kept."""
    return await LearningCourseAdminService.unpublish_course(db, tenant_id=principal.tenant_id, course_id=course_id)


@router.delete("/courses/{course_id}", response_model=MessageResponse)
async def delete_course(
    course_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a draft/unpublished course together with its learning records."""
    await LearningCourseAdminService.delete_course(db, tenant_id=principal.tenant_id, course_id=course_id)
    return MessageResponse(message="Deleted successfully")


@router.post("/courses/cover", response_model=CoverUploadResponse)
async def upload_cover(
    file: UploadFile = File(...),
    principal: EffectivePrincipal = ManageDep,
) -> CoverUploadResponse:
    """Upload a course cover image (small images go through the API to OSS)."""
    data = await file.read()
    url = await LearningCourseAdminService.upload_cover(
        tenant_id=principal.tenant_id,
        filename=file.filename or "cover.png",
        data=data,
        content_type=file.content_type or "",
    )
    return CoverUploadResponse(url=url)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


@router.post("/courses/{course_id}/sections", response_model=LearningSectionResponse, status_code=status.HTTP_201_CREATED)
async def create_section(
    course_id: int,
    body: LearningSectionCreate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningSectionResponse:
    """Append a section (default name 章节 N)."""
    return await LearningSectionAdminService.create_section(
        db, tenant_id=principal.tenant_id, course_id=course_id, name=body.name
    )


@router.put("/sections/{section_id}", response_model=LearningSectionResponse)
async def rename_section(
    section_id: int,
    body: LearningSectionUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningSectionResponse:
    return await LearningSectionAdminService.rename_section(
        db, tenant_id=principal.tenant_id, section_id=section_id, name=body.name
    )


@router.put("/courses/{course_id}/sections/order", response_model=MessageResponse)
async def reorder_sections(
    course_id: int,
    body: SectionOrderUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await LearningSectionAdminService.reorder_sections(
        db, tenant_id=principal.tenant_id, course_id=course_id, ordered_ids=body.ordered_ids
    )
    return MessageResponse(message="Reordered successfully")


@router.delete("/sections/{section_id}", response_model=MessageResponse)
async def delete_section(
    section_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await LearningSectionAdminService.delete_section(db, tenant_id=principal.tenant_id, section_id=section_id)
    return MessageResponse(message="Deleted successfully")


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------


@router.post("/materials/upload-credential", response_model=MaterialUploadCredentialResponse)
async def create_upload_credential(
    body: MaterialUploadCredentialRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MaterialUploadCredentialResponse:
    """Issue a direct-upload credential (VOD for video, OSS for audio/pdf/document)."""
    return await LearningMaterialAdminService.create_upload_credential(
        tenant_id=principal.tenant_id, data=body
    )


@router.post("/sections/{section_id}/materials", response_model=LearningMaterialResponse, status_code=status.HTTP_201_CREATED)
async def create_material(
    section_id: int,
    body: LearningMaterialCreate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningMaterialResponse:
    """Create a material record after the file was uploaded straight to the provider."""
    return await LearningMaterialAdminService.create_material(
        db, tenant_id=principal.tenant_id, section_id=section_id, data=body
    )


@router.put("/materials/{material_id}", response_model=LearningMaterialResponse)
async def rename_material(
    material_id: int,
    body: LearningMaterialUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningMaterialResponse:
    return await LearningMaterialAdminService.rename_material(
        db, tenant_id=principal.tenant_id, material_id=material_id, name=body.name
    )


@router.put("/sections/{section_id}/materials/order", response_model=MessageResponse)
async def reorder_materials(
    section_id: int,
    body: MaterialOrderUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await LearningMaterialAdminService.reorder_materials(
        db, tenant_id=principal.tenant_id, section_id=section_id, ordered_ids=body.ordered_ids
    )
    return MessageResponse(message="Reordered successfully")


@router.delete("/materials/{material_id}", response_model=MessageResponse)
async def delete_material(
    material_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await LearningMaterialAdminService.delete_material(db, tenant_id=principal.tenant_id, material_id=material_id)
    return MessageResponse(message="Deleted successfully")


@router.post("/materials/{material_id}/retranscode", response_model=LearningMaterialResponse)
async def retranscode_material(
    material_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningMaterialResponse:
    return await LearningMaterialAdminService.retranscode_material(
        db, tenant_id=principal.tenant_id, material_id=material_id
    )


# ---------------------------------------------------------------------------
# Visibility & assignments
# ---------------------------------------------------------------------------


@router.put("/courses/{course_id}/visibility", response_model=LearningCourseResponse)
async def update_visibility(
    course_id: int,
    body: LearningCourseVisibilityUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningCourseResponse:
    """Switch the course visibility (all employees / assigned learners)."""
    return await LearningAssignmentService.update_visibility(
        db, tenant_id=principal.tenant_id, course_id=course_id, visibility=body.visibility
    )


@router.get("/courses/{course_id}/assignments", response_model=AssignmentListResponse)
async def list_assignments(
    course_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignmentListResponse:
    """List assignment targets (groups / employees) with display data."""
    items = await LearningAssignmentService.list_assignments(
        db, tenant_id=principal.tenant_id, course_id=course_id
    )
    return AssignmentListResponse(items=items)


@router.post(
    "/courses/{course_id}/assignments",
    response_model=AssignmentAddResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_assignments(
    course_id: int,
    body: AssignmentAddRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignmentAddResponse:
    """Add assignment targets; already-existing targets are skipped."""
    added = await LearningAssignmentService.add_assignments(
        db, tenant_id=principal.tenant_id, course_id=course_id, targets=body.targets
    )
    return AssignmentAddResponse(added_count=added)


@router.delete("/courses/{course_id}/assignments/{assignment_id}", response_model=MessageResponse)
async def remove_assignment(
    course_id: int,
    assignment_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await LearningAssignmentService.remove_assignment(
        db, tenant_id=principal.tenant_id, course_id=course_id, assignment_id=assignment_id
    )
    return MessageResponse(message="Removed successfully")


@router.get("/courses/{course_id}/assignable-groups", response_model=AssignableGroupListResponse)
async def list_assignable_groups(
    course_id: int,
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignableGroupListResponse:
    """Group picker data for the add-learners dialog."""
    items = await LearningAssignmentService.list_assignable_groups(
        db, tenant_id=principal.tenant_id, course_id=course_id, q=q
    )
    return AssignableGroupListResponse(items=items)


@router.get("/courses/{course_id}/assignable-employees", response_model=AssignableEmployeeListResponse)
async def list_assignable_employees(
    course_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignableEmployeeListResponse:
    """Employee picker data for the add-learners dialog."""
    return await LearningAssignmentService.list_assignable_employees(
        db, tenant_id=principal.tenant_id, course_id=course_id, q=q, page=page, per_page=per_page
    )


@router.get("/courses/{course_id}/learners", response_model=LearnerListResponse)
async def list_learners(
    course_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearnerListResponse:
    """Learner progress table (all employees or assigned audience, per visibility)."""
    return await LearningAssignmentService.list_learners(
        db, tenant_id=principal.tenant_id, course_id=course_id, q=q, page=page, per_page=per_page
    )
