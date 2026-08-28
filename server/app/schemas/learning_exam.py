"""
Learning center exam schemas: exam admin APIs (exam/question CRUD, lifecycle)
and the employee-side taking/result views.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse


# ---------------------------------------------------------------------------
# Exam (admin)
# ---------------------------------------------------------------------------


class LearningExamCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)


class LearningExamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    intro: str | None = Field(default=None, max_length=200)
    pass_percent: int | None = Field(default=None, ge=1, le=100)
    time_limit_minutes: int | None = Field(default=None, ge=1, le=180)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    shuffle_questions: bool | None = None


class LearningExamVisibilityUpdate(BaseModel):
    visibility: str = Field(pattern="^(all|assigned)$")


class LearningExamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    intro: str | None = None
    status: str
    visibility: str
    pass_percent: int
    time_limit_minutes: int | None = None
    max_attempts: int
    shuffle_questions: bool
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminExamListItem(BaseModel):
    id: int
    name: str
    status: str
    visibility: str
    question_count: int
    total_score: int
    pass_score: int
    # None means "all employees" for visibility=all exams.
    learner_count: int | None = None
    passed_count: int
    updated_at: datetime | None = None


class AdminExamListResponse(PaginatedResponse):
    items: list[AdminExamListItem]


# ---------------------------------------------------------------------------
# Question (admin)
# ---------------------------------------------------------------------------


class ExamQuestionOption(BaseModel):
    key: str = Field(min_length=1, max_length=8)
    # Judge options omit text; their labels are rendered by the frontend.
    text: str | None = Field(default=None, max_length=200)
    is_correct: bool = False


class LearningExamQuestionCreate(BaseModel):
    type: str = Field(pattern="^(single|multiple|judge)$")
    stem: str = Field(min_length=1, max_length=500)
    score: int = Field(ge=1, le=100)
    options: list[ExamQuestionOption] = Field(min_length=2, max_length=6)


class LearningExamQuestionUpdate(BaseModel):
    type: str | None = Field(default=None, pattern="^(single|multiple|judge)$")
    stem: str | None = Field(default=None, min_length=1, max_length=500)
    score: int | None = Field(default=None, ge=1, le=100)
    options: list[ExamQuestionOption] | None = Field(default=None, min_length=2, max_length=6)


class LearningExamQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exam_id: int
    type: str
    stem: str
    score: int
    options: list[ExamQuestionOption]
    sort_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QuestionOrderUpdate(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class LearningExamDetail(LearningExamResponse):
    questions: list[LearningExamQuestionResponse] = []


# ---------------------------------------------------------------------------
# Learner results (admin)
# ---------------------------------------------------------------------------


class ExamResultItem(BaseModel):
    employee_id: int
    name: str
    group_names: list[str] = []
    direct_assigned: bool = False
    assigned_group_names: list[str] = []
    best_score: int | None = None
    status: str  # not_started | passed | failed
    submitted_count: int = 0
    last_submitted_at: datetime | None = None


class ExamResultListResponse(PaginatedResponse):
    items: list[ExamResultItem]


# ---------------------------------------------------------------------------
# My exams (employee)
# ---------------------------------------------------------------------------


class MyExamItem(BaseModel):
    id: int
    name: str
    intro: str | None = None
    question_count: int
    total_score: int
    pass_score: int
    pass_percent: int
    time_limit_minutes: int | None = None
    max_attempts: int
    best_score: int | None = None
    status: str  # not_started | passed | failed
    remaining_attempts: int
    updated_at: datetime | None = None


class MyExamListResponse(PaginatedResponse):
    items: list[MyExamItem]


class MyExamAttemptHistoryItem(BaseModel):
    id: int
    attempt_index: int
    score: int
    passed: bool
    submitted_at: datetime | None = None


class MyExamSummary(BaseModel):
    """My-exam detail: exam rules + best score + submitted attempt history."""

    id: int
    name: str
    intro: str | None = None
    question_count: int
    total_score: int
    pass_score: int
    pass_percent: int
    time_limit_minutes: int | None = None
    max_attempts: int
    shuffle_questions: bool
    best_score: int | None = None
    status: str  # not_started | passed | failed
    remaining_attempts: int
    # Best submitted attempt id (ties resolved by most recent), for the default review.
    best_attempt_id: int | None = None
    attempts: list[MyExamAttemptHistoryItem] = []


# ---------------------------------------------------------------------------
# Attempts (employee taking / review)
# ---------------------------------------------------------------------------


class AttemptQuestionOption(BaseModel):
    key: str
    # Judge options omit text; labels are rendered by the frontend.
    text: str | None = None
    # Only present in review responses (submitted attempts), never while taking.
    is_correct: bool | None = None


class AttemptQuestion(BaseModel):
    question_id: int
    type: str
    stem: str
    score: int
    options: list[AttemptQuestionOption]
    # Review-only fields.
    selected_keys: list[str] | None = None
    correct_keys: list[str] | None = None
    gained_score: int | None = None
    is_correct: bool | None = None


class AttemptStartResponse(BaseModel):
    attempt_id: int
    exam_id: int
    started_at: datetime
    time_limit_minutes: int | None = None
    questions: list[AttemptQuestion]


class AttemptDetailResponse(BaseModel):
    """Attempt state for the taking page (in_progress) or the review page (submitted)."""

    attempt_id: int
    exam_id: int
    status: str
    attempt_index: int | None = None
    score: int | None = None
    passed: bool | None = None
    started_at: datetime
    submitted_at: datetime | None = None
    time_limit_minutes: int | None = None
    questions: list[AttemptQuestion]


class AttemptSubmitRequest(BaseModel):
    # Map of question_id -> selected option keys. Missing entries count as unanswered.
    answers: dict[str, list[str]] = {}


class AttemptSubmitResponse(BaseModel):
    attempt_id: int
    exam_id: int
    attempt_index: int
    score: int
    total_score: int
    pass_score: int
    passed: bool
    submitted_at: datetime
