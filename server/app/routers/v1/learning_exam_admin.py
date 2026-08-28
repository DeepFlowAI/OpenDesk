"""
Learning center exam admin router: exam/question management for tenants.

All endpoints require the ``learning.exam.manage`` permission.
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import EffectivePrincipal, get_db, require_permission
from app.schemas.learning import (
    AssignableEmployeeListResponse,
    AssignableGroupListResponse,
    AssignmentAddRequest,
    AssignmentAddResponse,
    AssignmentListResponse,
    MessageResponse,
)
from app.schemas.learning_exam import (
    AdminExamListResponse,
    ExamResultListResponse,
    LearningExamCreate,
    LearningExamDetail,
    LearningExamQuestionCreate,
    LearningExamQuestionResponse,
    LearningExamQuestionUpdate,
    LearningExamResponse,
    LearningExamUpdate,
    LearningExamVisibilityUpdate,
    QuestionOrderUpdate,
)
from app.services.learning_exam_admin_service import (
    LearningExamAdminService,
    LearningExamQuestionAdminService,
)
from app.services.learning_exam_assignment_service import LearningExamAssignmentService

router = APIRouter(prefix="/learning/admin", tags=["Learning Exam Admin"])

ManageDep = Depends(require_permission("learning.exam.manage"))


@router.get("/exams", response_model=AdminExamListResponse)
async def list_exams(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AdminExamListResponse:
    """List exams with question/learner stats for the admin table."""
    return await LearningExamAdminService.list_exams(
        db, tenant_id=principal.tenant_id, page=page, per_page=per_page, q=q, status=status
    )


@router.post("/exams", response_model=LearningExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(
    body: LearningExamCreate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningExamResponse:
    """Create an exam (starts as draft, defaults to 未命名考试)."""
    return await LearningExamAdminService.create_exam(
        db, tenant_id=principal.tenant_id, employee_id=principal.user_id, data=body
    )


@router.get("/exams/{exam_id}", response_model=LearningExamDetail)
async def get_exam(
    exam_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningExamDetail:
    """Exam detail with the ordered question list for the edit page."""
    return await LearningExamAdminService.get_exam_detail(db, tenant_id=principal.tenant_id, exam_id=exam_id)


@router.put("/exams/{exam_id}", response_model=LearningExamResponse)
async def update_exam(
    exam_id: int,
    body: LearningExamUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningExamResponse:
    """Update basic info and settings (name/intro/duration/pass percent/attempts/shuffle)."""
    return await LearningExamAdminService.update_exam(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, data=body
    )


@router.post("/exams/{exam_id}/publish", response_model=LearningExamResponse)
async def publish_exam(
    exam_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningExamResponse:
    """Publish an exam (requires at least one question with total score > 0)."""
    return await LearningExamAdminService.publish_exam(db, tenant_id=principal.tenant_id, exam_id=exam_id)


@router.post("/exams/{exam_id}/unpublish", response_model=LearningExamResponse)
async def unpublish_exam(
    exam_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningExamResponse:
    """Unpublish an exam; existing attempts and scores are kept."""
    return await LearningExamAdminService.unpublish_exam(db, tenant_id=principal.tenant_id, exam_id=exam_id)


@router.delete("/exams/{exam_id}", response_model=MessageResponse)
async def delete_exam(
    exam_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a draft/unpublished exam together with questions, assignments and attempts."""
    await LearningExamAdminService.delete_exam(db, tenant_id=principal.tenant_id, exam_id=exam_id)
    return MessageResponse(message="Deleted successfully")


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@router.post(
    "/exams/{exam_id}/questions",
    response_model=LearningExamQuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_question(
    exam_id: int,
    body: LearningExamQuestionCreate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningExamQuestionResponse:
    """Append a question to the exam."""
    return await LearningExamQuestionAdminService.create_question(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, data=body
    )


@router.put("/exam-questions/{question_id}", response_model=LearningExamQuestionResponse)
async def update_question(
    question_id: int,
    body: LearningExamQuestionUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningExamQuestionResponse:
    return await LearningExamQuestionAdminService.update_question(
        db, tenant_id=principal.tenant_id, question_id=question_id, data=body
    )


@router.put("/exams/{exam_id}/questions/order", response_model=MessageResponse)
async def reorder_questions(
    exam_id: int,
    body: QuestionOrderUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await LearningExamQuestionAdminService.reorder_questions(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, ordered_ids=body.ordered_ids
    )
    return MessageResponse(message="Reordered successfully")


@router.delete("/exam-questions/{question_id}", response_model=MessageResponse)
async def delete_question(
    question_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await LearningExamQuestionAdminService.delete_question(db, tenant_id=principal.tenant_id, question_id=question_id)
    return MessageResponse(message="Deleted successfully")


# ---------------------------------------------------------------------------
# Visibility, assignments & results
# ---------------------------------------------------------------------------


@router.put("/exams/{exam_id}/visibility", response_model=LearningExamResponse)
async def update_exam_visibility(
    exam_id: int,
    body: LearningExamVisibilityUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> LearningExamResponse:
    """Switch the exam visibility (all employees / assigned learners)."""
    return await LearningExamAssignmentService.update_visibility(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, visibility=body.visibility
    )


@router.get("/exams/{exam_id}/assignments", response_model=AssignmentListResponse)
async def list_exam_assignments(
    exam_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignmentListResponse:
    """List assignment targets (groups / employees) with display data."""
    items = await LearningExamAssignmentService.list_assignments(
        db, tenant_id=principal.tenant_id, exam_id=exam_id
    )
    return AssignmentListResponse(items=items)


@router.post(
    "/exams/{exam_id}/assignments",
    response_model=AssignmentAddResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_exam_assignments(
    exam_id: int,
    body: AssignmentAddRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignmentAddResponse:
    """Add assignment targets; already-existing targets are skipped."""
    added = await LearningExamAssignmentService.add_assignments(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, targets=body.targets
    )
    return AssignmentAddResponse(added_count=added)


@router.delete("/exams/{exam_id}/assignments/{assignment_id}", response_model=MessageResponse)
async def remove_exam_assignment(
    exam_id: int,
    assignment_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await LearningExamAssignmentService.remove_assignment(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, assignment_id=assignment_id
    )
    return MessageResponse(message="Removed successfully")


@router.get("/exams/{exam_id}/assignable-groups", response_model=AssignableGroupListResponse)
async def list_exam_assignable_groups(
    exam_id: int,
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignableGroupListResponse:
    """Group picker data for the add-learners dialog."""
    items = await LearningExamAssignmentService.list_assignable_groups(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, q=q
    )
    return AssignableGroupListResponse(items=items)


@router.get("/exams/{exam_id}/assignable-employees", response_model=AssignableEmployeeListResponse)
async def list_exam_assignable_employees(
    exam_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignableEmployeeListResponse:
    """Employee picker data for the add-learners dialog."""
    return await LearningExamAssignmentService.list_assignable_employees(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, q=q, page=page, per_page=per_page
    )


@router.get("/exams/{exam_id}/results", response_model=ExamResultListResponse)
async def list_exam_results(
    exam_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> ExamResultListResponse:
    """Learner results table (all employees or assigned audience, per visibility)."""
    return await LearningExamAssignmentService.list_results(
        db, tenant_id=principal.tenant_id, exam_id=exam_id, q=q, page=page, per_page=per_page
    )
