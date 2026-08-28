"""
Learning center exam admin service: exam lifecycle and question management.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.models.learning_exam import (
    EXAM_STATUS_PUBLISHED,
    JUDGE_OPTION_KEYS,
    QUESTION_TYPE_JUDGE,
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_SINGLE,
    LearningExam,
    LearningExamQuestion,
)
from app.repositories.learning_exam_repository import (
    LearningExamAssignmentRepository,
    LearningExamAttemptRepository,
    LearningExamQuestionRepository,
    LearningExamRepository,
)
from app.schemas.learning_exam import (
    ExamQuestionOption,
    LearningExamCreate,
    LearningExamQuestionCreate,
    LearningExamQuestionUpdate,
    LearningExamUpdate,
)

DEFAULT_EXAM_NAME = "未命名考试"


def pass_score_of(total_score: int, pass_percent: int) -> int:
    """Pass mark per PRD: floor(total * percent / 100)."""
    return total_score * pass_percent // 100


class LearningExamAdminService:
    """Exam lifecycle for tenant admins (learning.exam.manage)."""

    @staticmethod
    async def list_exams(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int,
        per_page: int,
        q: str | None,
        status: str | None,
    ) -> dict:
        exams, total = await LearningExamRepository.list_paginated(
            db, tenant_id, page, per_page, q=q, status=status
        )
        exam_ids = [exam.id for exam in exams]
        question_stats = await LearningExamRepository.aggregate_questions_by_exam(db, exam_ids)
        passed_counts = await LearningExamAttemptRepository.count_passed_employees_by_exam(db, exam_ids)

        items = []
        for exam in exams:
            stats = question_stats.get(exam.id, {"question_count": 0, "total_score": 0})
            if exam.visibility == "all":
                # None renders as "全员" in the admin table.
                learner_count: int | None = None
            else:
                visible_ids = await LearningExamAssignmentRepository.list_visible_employee_ids(
                    db, tenant_id, exam.id
                )
                learner_count = len(visible_ids)
            items.append(
                {
                    "id": exam.id,
                    "name": exam.name,
                    "status": exam.status,
                    "visibility": exam.visibility,
                    "question_count": stats["question_count"],
                    "total_score": stats["total_score"],
                    "pass_score": pass_score_of(stats["total_score"], exam.pass_percent),
                    "learner_count": learner_count,
                    "passed_count": passed_counts.get(exam.id, 0),
                    "updated_at": exam.updated_at,
                }
            )
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if per_page else 0,
        }

    @staticmethod
    async def create_exam(
        db: AsyncSession, *, tenant_id: int, employee_id: int, data: LearningExamCreate
    ) -> LearningExam:
        return await LearningExamRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": (data.name or DEFAULT_EXAM_NAME).strip() or DEFAULT_EXAM_NAME,
                "created_by": employee_id,
            },
        )

    @staticmethod
    async def get_exam_detail(db: AsyncSession, *, tenant_id: int, exam_id: int) -> dict:
        exam = await _get_exam_or_404(db, tenant_id, exam_id)
        questions = await LearningExamQuestionRepository.list_by_exam(db, exam.id)
        return {**{c.name: getattr(exam, c.name) for c in LearningExam.__table__.columns}, "questions": questions}

    @staticmethod
    async def update_exam(
        db: AsyncSession, *, tenant_id: int, exam_id: int, data: LearningExamUpdate
    ) -> LearningExam:
        exam = await _get_exam_or_404(db, tenant_id, exam_id)
        payload = data.model_dump(exclude_unset=True)
        # Explicit null clears nullable fields only; never null out required ones.
        for required_key in ("name", "pass_percent", "max_attempts", "shuffle_questions"):
            if payload.get(required_key) is None:
                payload.pop(required_key, None)
        if payload.get("intro") == "":
            payload["intro"] = None
        if isinstance(payload.get("name"), str):
            payload["name"] = payload["name"].strip()
        if not payload:
            return exam
        return await LearningExamRepository.update(db, exam, payload)

    @staticmethod
    async def publish_exam(db: AsyncSession, *, tenant_id: int, exam_id: int) -> LearningExam:
        exam = await _get_exam_or_404(db, tenant_id, exam_id)
        if exam.status == EXAM_STATUS_PUBLISHED:
            return exam
        stats = (await LearningExamRepository.aggregate_questions_by_exam(db, [exam.id])).get(
            exam.id, {"question_count": 0, "total_score": 0}
        )
        if stats["question_count"] < 1 or stats["total_score"] <= 0:
            raise BusinessError(
                "Add at least one question before publishing",
                status_code=400,
                code="EXAM_NOT_READY",
            )
        return await LearningExamRepository.update(db, exam, {"status": EXAM_STATUS_PUBLISHED})

    @staticmethod
    async def unpublish_exam(db: AsyncSession, *, tenant_id: int, exam_id: int) -> LearningExam:
        exam = await _get_exam_or_404(db, tenant_id, exam_id)
        if exam.status != EXAM_STATUS_PUBLISHED:
            return exam
        return await LearningExamRepository.update(db, exam, {"status": "unpublished"})

    @staticmethod
    async def delete_exam(db: AsyncSession, *, tenant_id: int, exam_id: int) -> None:
        exam = await _get_exam_or_404(db, tenant_id, exam_id)
        if exam.status == EXAM_STATUS_PUBLISHED:
            raise BusinessError(
                "Published exams cannot be deleted; unpublish first",
                status_code=400,
                code="EXAM_NOT_DELETABLE",
            )
        await LearningExamRepository.delete(db, exam)


class LearningExamQuestionAdminService:
    """Question management inside one exam."""

    @staticmethod
    async def create_question(
        db: AsyncSession, *, tenant_id: int, exam_id: int, data: LearningExamQuestionCreate
    ) -> LearningExamQuestion:
        await _get_exam_or_404(db, tenant_id, exam_id)
        options = _validate_and_normalize_options(data.type, data.options)
        sort_order = await LearningExamQuestionRepository.next_sort_order(db, exam_id)
        return await LearningExamQuestionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "exam_id": exam_id,
                "type": data.type,
                "stem": data.stem.strip(),
                "score": data.score,
                "options": options,
                "sort_order": sort_order,
            },
        )

    @staticmethod
    async def update_question(
        db: AsyncSession, *, tenant_id: int, question_id: int, data: LearningExamQuestionUpdate
    ) -> LearningExamQuestion:
        question = await _get_question_or_404(db, tenant_id, question_id)
        payload = data.model_dump(exclude_unset=True)

        new_type = payload.get("type") or question.type
        new_options_raw = payload.get("options")
        if new_options_raw is not None or "type" in payload:
            base_options = (
                new_options_raw
                if new_options_raw is not None
                else [ExamQuestionOption(**opt) for opt in question.options]
            )
            payload["options"] = _validate_and_normalize_options(new_type, base_options)
        if isinstance(payload.get("stem"), str):
            payload["stem"] = payload["stem"].strip()
        if not payload:
            return question
        return await LearningExamQuestionRepository.update(db, question, payload)

    @staticmethod
    async def reorder_questions(
        db: AsyncSession, *, tenant_id: int, exam_id: int, ordered_ids: list[int]
    ) -> None:
        await _get_exam_or_404(db, tenant_id, exam_id)
        existing = await LearningExamQuestionRepository.list_by_exam(db, exam_id)
        existing_ids = [question.id for question in existing]
        if set(ordered_ids) != set(existing_ids) or len(ordered_ids) != len(existing_ids):
            raise ValidationError("ordered_ids must match the existing items exactly")
        await LearningExamQuestionRepository.apply_order(db, exam_id, ordered_ids)

    @staticmethod
    async def delete_question(db: AsyncSession, *, tenant_id: int, question_id: int) -> None:
        question = await _get_question_or_404(db, tenant_id, question_id)
        await LearningExamQuestionRepository.delete(db, question)


def _validate_and_normalize_options(
    question_type: str, options: list[ExamQuestionOption]
) -> list[dict]:
    """Validate option rules per question type and return JSON-ready dicts."""
    if question_type == QUESTION_TYPE_JUDGE:
        keys = {opt.key for opt in options}
        if len(options) != 2 or keys != JUDGE_OPTION_KEYS:
            raise ValidationError("Judge questions must have exactly the true/false options")
        correct_count = sum(1 for opt in options if opt.is_correct)
        if correct_count != 1:
            raise ValidationError("Judge questions must mark exactly one correct option")
        return [{"key": opt.key, "text": None, "is_correct": opt.is_correct} for opt in options]

    keys = [opt.key for opt in options]
    if len(set(keys)) != len(keys):
        raise ValidationError("Option keys must be unique within a question")
    normalized = []
    for opt in options:
        text = (opt.text or "").strip()
        if not text:
            raise ValidationError("Option text is required")
        normalized.append({"key": opt.key, "text": text, "is_correct": opt.is_correct})
    correct_count = sum(1 for opt in normalized if opt["is_correct"])
    if question_type == QUESTION_TYPE_SINGLE and correct_count != 1:
        raise ValidationError("Single-choice questions must mark exactly one correct option")
    if question_type == QUESTION_TYPE_MULTIPLE and correct_count < 2:
        raise ValidationError("Multiple-choice questions must mark at least two correct options")
    return normalized


async def _get_exam_or_404(db: AsyncSession, tenant_id: int, exam_id: int) -> LearningExam:
    exam = await LearningExamRepository.get_by_id(db, tenant_id, exam_id)
    if exam is None:
        raise NotFoundError("Exam not found")
    return exam


async def _get_question_or_404(db: AsyncSession, tenant_id: int, question_id: int) -> LearningExamQuestion:
    question = await LearningExamQuestionRepository.get_by_id(db, tenant_id, question_id)
    if question is None:
        raise NotFoundError("Question not found")
    return question
