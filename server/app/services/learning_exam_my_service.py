"""
Learning center employee-side exam service: my exams, attempt lifecycle
(start/take/submit/abandon), auto grading and attempt review.
"""
import random
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError
from app.models.learning import VISIBILITY_ALL
from app.models.learning_exam import (
    ATTEMPT_STATUS_ABANDONED,
    ATTEMPT_STATUS_IN_PROGRESS,
    ATTEMPT_STATUS_SUBMITTED,
    EXAM_STATUS_PUBLISHED,
    LearningExam,
    LearningExamAttempt,
)
from app.repositories.learning_exam_repository import (
    LearningExamAssignmentRepository,
    LearningExamAttemptRepository,
    LearningExamQuestionRepository,
    LearningExamRepository,
)
from app.services.learning_exam_admin_service import pass_score_of


class LearningExamMyService:
    @staticmethod
    async def list_my_exams(
        db: AsyncSession,
        *,
        tenant_id: int,
        employee_id: int,
        q: str | None,
        page: int,
        per_page: int,
    ) -> dict:
        exams, _total = await LearningExamRepository.list_paginated(
            db, tenant_id, page=1, per_page=10000, q=q, status=EXAM_STATUS_PUBLISHED
        )
        assigned_exams = [exam for exam in exams if exam.visibility != VISIBILITY_ALL]
        visible_map = await LearningExamAssignmentRepository.expand_assignments(
            db, tenant_id, [exam.id for exam in assigned_exams]
        )
        visible_exams = [
            exam
            for exam in exams
            if exam.visibility == VISIBILITY_ALL or employee_id in visible_map.get(exam.id, set())
        ]

        exam_ids = [exam.id for exam in visible_exams]
        question_stats = await LearningExamRepository.aggregate_questions_by_exam(db, exam_ids)
        attempt_stats = await LearningExamAttemptRepository.aggregate_by_exams_for_employee(
            db, exam_ids, employee_id
        )

        items = []
        for exam in visible_exams:
            stats = question_stats.get(exam.id, {"question_count": 0, "total_score": 0})
            agg = attempt_stats.get(exam.id, {"submitted_count": 0, "best_score": None})
            pass_score = pass_score_of(stats["total_score"], exam.pass_percent)
            items.append(
                {
                    "id": exam.id,
                    "name": exam.name,
                    "intro": exam.intro,
                    "question_count": stats["question_count"],
                    "total_score": stats["total_score"],
                    "pass_score": pass_score,
                    "pass_percent": exam.pass_percent,
                    "time_limit_minutes": exam.time_limit_minutes,
                    "max_attempts": exam.max_attempts,
                    "best_score": agg["best_score"],
                    "status": _aggregate_status(agg["submitted_count"], agg["best_score"], pass_score),
                    "remaining_attempts": max(exam.max_attempts - agg["submitted_count"], 0),
                    "updated_at": exam.updated_at,
                }
            )

        total = len(items)
        window = items[(page - 1) * per_page : page * per_page]
        return {
            "items": window,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if per_page else 0,
        }

    @staticmethod
    async def get_my_exam_summary(
        db: AsyncSession, *, tenant_id: int, exam_id: int, employee_id: int
    ) -> dict:
        exam = await _get_visible_exam_or_404(db, tenant_id, exam_id, employee_id)
        stats = (await LearningExamRepository.aggregate_questions_by_exam(db, [exam.id])).get(
            exam.id, {"question_count": 0, "total_score": 0}
        )
        pass_score = pass_score_of(stats["total_score"], exam.pass_percent)

        submitted = await LearningExamAttemptRepository.list_submitted_by_exam_employee(
            db, exam.id, employee_id
        )
        history = sorted(submitted, key=lambda attempt: attempt.attempt_index)
        best_attempt = _best_attempt(submitted)
        best_score = best_attempt.score if best_attempt else None

        return {
            "id": exam.id,
            "name": exam.name,
            "intro": exam.intro,
            "question_count": stats["question_count"],
            "total_score": stats["total_score"],
            "pass_score": pass_score,
            "pass_percent": exam.pass_percent,
            "time_limit_minutes": exam.time_limit_minutes,
            "max_attempts": exam.max_attempts,
            "shuffle_questions": exam.shuffle_questions,
            "best_score": best_score,
            "status": _aggregate_status(len(submitted), best_score, pass_score),
            "remaining_attempts": max(exam.max_attempts - len(submitted), 0),
            "best_attempt_id": best_attempt.id if best_attempt else None,
            "attempts": [
                {
                    "id": attempt.id,
                    "attempt_index": attempt.attempt_index,
                    "score": attempt.score,
                    "passed": attempt.passed,
                    "submitted_at": attempt.submitted_at,
                }
                for attempt in history
            ],
        }

    @staticmethod
    async def start_attempt(
        db: AsyncSession, *, tenant_id: int, exam_id: int, employee_id: int
    ) -> dict:
        exam = await _get_visible_exam_or_404(db, tenant_id, exam_id, employee_id)
        submitted = await LearningExamAttemptRepository.list_submitted_by_exam_employee(
            db, exam.id, employee_id
        )
        if len(submitted) >= exam.max_attempts:
            raise BusinessError(
                "No attempts remaining for this exam",
                status_code=400,
                code="EXAM_NO_ATTEMPTS_LEFT",
            )

        # Abandon any lingering in-progress attempt left by an interrupted session.
        await LearningExamAttemptRepository.abandon_in_progress(db, exam.id, employee_id)

        questions = await LearningExamQuestionRepository.list_by_exam(db, exam.id)
        snapshot = [
            {
                "question_id": question.id,
                "type": question.type,
                "stem": question.stem,
                "score": question.score,
                "options": [
                    {"key": opt.get("key"), "text": opt.get("text"), "is_correct": bool(opt.get("is_correct"))}
                    for opt in (question.options or [])
                ],
            }
            for question in questions
        ]
        if exam.shuffle_questions:
            random.shuffle(snapshot)

        attempt = await LearningExamAttemptRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "exam_id": exam.id,
                "employee_id": employee_id,
                "status": ATTEMPT_STATUS_IN_PROGRESS,
                "snapshot": snapshot,
                "answers": {},
                "started_at": datetime.now(timezone.utc),
            },
        )
        return {
            "attempt_id": attempt.id,
            "exam_id": exam.id,
            "started_at": attempt.started_at,
            "time_limit_minutes": exam.time_limit_minutes,
            "questions": [_taking_question(entry) for entry in snapshot],
        }

    @staticmethod
    async def get_attempt_detail(
        db: AsyncSession, *, tenant_id: int, attempt_id: int, employee_id: int
    ) -> dict:
        attempt = await _get_my_attempt_or_404(db, tenant_id, attempt_id, employee_id)
        if attempt.status == ATTEMPT_STATUS_ABANDONED:
            raise NotFoundError("Attempt not found")

        exam = await LearningExamRepository.get_by_id(db, tenant_id, attempt.exam_id)
        time_limit = exam.time_limit_minutes if exam else None
        base = {
            "attempt_id": attempt.id,
            "exam_id": attempt.exam_id,
            "status": attempt.status,
            "attempt_index": attempt.attempt_index,
            "score": attempt.score,
            "passed": attempt.passed,
            "started_at": attempt.started_at,
            "submitted_at": attempt.submitted_at,
            "time_limit_minutes": time_limit,
        }
        if attempt.status == ATTEMPT_STATUS_IN_PROGRESS:
            # Never leak answers while taking.
            return {**base, "score": None, "passed": None, "questions": [_taking_question(entry) for entry in attempt.snapshot]}
        return {**base, "questions": _review_questions(attempt)}

    @staticmethod
    async def submit_attempt(
        db: AsyncSession, *, tenant_id: int, attempt_id: int, employee_id: int, answers: dict[str, list[str]]
    ) -> dict:
        attempt = await _get_my_attempt_or_404(db, tenant_id, attempt_id, employee_id)
        if attempt.status != ATTEMPT_STATUS_IN_PROGRESS:
            raise BusinessError(
                "Attempt is not submittable",
                status_code=400,
                code="ATTEMPT_NOT_SUBMITTABLE",
            )

        snapshot = attempt.snapshot or []
        total_score = sum(entry["score"] for entry in snapshot)
        gained = 0
        for entry in snapshot:
            selected = set(answers.get(str(entry["question_id"])) or [])
            correct = {opt["key"] for opt in entry["options"] if opt.get("is_correct")}
            if selected == correct:
                gained += entry["score"]

        exam = await LearningExamRepository.get_by_id(db, tenant_id, attempt.exam_id)
        pass_percent = exam.pass_percent if exam else 60
        pass_score = pass_score_of(total_score, pass_percent)

        submitted_count = len(
            await LearningExamAttemptRepository.list_submitted_by_exam_employee(
                db, attempt.exam_id, employee_id
            )
        )
        now = datetime.now(timezone.utc)
        attempt.status = ATTEMPT_STATUS_SUBMITTED
        attempt.attempt_index = submitted_count + 1
        attempt.answers = {str(key): value for key, value in answers.items()}
        attempt.score = gained
        attempt.passed = gained >= pass_score
        attempt.submitted_at = now
        attempt = await LearningExamAttemptRepository.save(db, attempt)

        return {
            "attempt_id": attempt.id,
            "exam_id": attempt.exam_id,
            "attempt_index": attempt.attempt_index,
            "score": gained,
            "total_score": total_score,
            "pass_score": pass_score,
            "passed": attempt.passed,
            "submitted_at": attempt.submitted_at,
        }

    @staticmethod
    async def abandon_attempt(
        db: AsyncSession, *, tenant_id: int, attempt_id: int, employee_id: int
    ) -> None:
        attempt = await _get_my_attempt_or_404(db, tenant_id, attempt_id, employee_id)
        if attempt.status != ATTEMPT_STATUS_IN_PROGRESS:
            return
        attempt.status = ATTEMPT_STATUS_ABANDONED
        await LearningExamAttemptRepository.save(db, attempt)


def _aggregate_status(submitted_count: int, best_score: int | None, pass_score: int) -> str:
    if submitted_count == 0 or best_score is None:
        return "not_started"
    return "passed" if best_score >= pass_score else "failed"


def _best_attempt(submitted: list[LearningExamAttempt]) -> LearningExamAttempt | None:
    """Highest score; ties resolve to the most recent submission."""
    if not submitted:
        return None
    return max(submitted, key=lambda attempt: (attempt.score, attempt.submitted_at or attempt.started_at))


def _taking_question(entry: dict) -> dict:
    """Snapshot entry for the taking page: correctness stripped."""
    return {
        "question_id": entry["question_id"],
        "type": entry["type"],
        "stem": entry["stem"],
        "score": entry["score"],
        "options": [{"key": opt["key"], "text": opt.get("text")} for opt in entry["options"]],
    }


def _review_questions(attempt: LearningExamAttempt) -> list[dict]:
    """Snapshot entries enriched with my answers and per-question grading."""
    answers = attempt.answers or {}
    questions = []
    for entry in attempt.snapshot or []:
        selected = sorted(set(answers.get(str(entry["question_id"])) or []))
        correct = sorted({opt["key"] for opt in entry["options"] if opt.get("is_correct")})
        gained = entry["score"] if set(selected) == set(correct) else 0
        questions.append(
            {
                "question_id": entry["question_id"],
                "type": entry["type"],
                "stem": entry["stem"],
                "score": entry["score"],
                "options": [
                    {"key": opt["key"], "text": opt.get("text"), "is_correct": bool(opt.get("is_correct"))}
                    for opt in entry["options"]
                ],
                "selected_keys": selected,
                "correct_keys": correct,
                "gained_score": gained,
                "is_correct": gained > 0,
            }
        )
    return questions


async def _get_visible_exam_or_404(
    db: AsyncSession, tenant_id: int, exam_id: int, employee_id: int
) -> LearningExam:
    exam = await LearningExamRepository.get_by_id(db, tenant_id, exam_id)
    if exam is None or exam.status != EXAM_STATUS_PUBLISHED:
        raise NotFoundError("Exam not found")
    if exam.visibility != VISIBILITY_ALL:
        visible = await LearningExamAssignmentRepository.list_visible_employee_ids(
            db, tenant_id, exam.id
        )
        if employee_id not in visible:
            raise NotFoundError("Exam not found")
    return exam


async def _get_my_attempt_or_404(
    db: AsyncSession, tenant_id: int, attempt_id: int, employee_id: int
) -> LearningExamAttempt:
    attempt = await LearningExamAttemptRepository.get_by_id(db, tenant_id, attempt_id)
    if attempt is None or attempt.employee_id != employee_id:
        raise NotFoundError("Attempt not found")
    return attempt
