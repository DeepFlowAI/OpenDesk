"""
Learning center exam domain models: exams, questions, assignment targets
and per-employee exam attempts with question snapshots.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin

EXAM_STATUS_DRAFT = "draft"
EXAM_STATUS_PUBLISHED = "published"
EXAM_STATUS_UNPUBLISHED = "unpublished"
EXAM_STATUSES = {EXAM_STATUS_DRAFT, EXAM_STATUS_PUBLISHED, EXAM_STATUS_UNPUBLISHED}

QUESTION_TYPE_SINGLE = "single"
QUESTION_TYPE_MULTIPLE = "multiple"
QUESTION_TYPE_JUDGE = "judge"
QUESTION_TYPES = {QUESTION_TYPE_SINGLE, QUESTION_TYPE_MULTIPLE, QUESTION_TYPE_JUDGE}

ATTEMPT_STATUS_IN_PROGRESS = "in_progress"
ATTEMPT_STATUS_SUBMITTED = "submitted"
ATTEMPT_STATUS_ABANDONED = "abandoned"

# Judge questions have two fixed options keyed "true"/"false"; their labels
# are rendered by the frontend via i18n instead of being stored.
JUDGE_OPTION_KEYS = {"true", "false"}


class LearningExam(Base, TimestampMixin):
    """An exam owned by a tenant (questions live inside the exam)."""

    __tablename__ = "learning_exams"
    __table_args__ = (
        Index("ix_learning_exams_tenant_status", "tenant_id", "status"),
        Index("ix_learning_exams_tenant_updated", "tenant_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    intro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EXAM_STATUS_DRAFT, server_default=EXAM_STATUS_DRAFT
    )
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="assigned", server_default="assigned"
    )
    pass_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default="60")
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    shuffle_questions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )


class LearningExamQuestion(Base, TimestampMixin):
    """An objective question inside an exam; options stored as a JSON document."""

    __tablename__ = "learning_exam_questions"
    __table_args__ = (
        Index("ix_learning_exam_questions_exam_sort", "exam_id", "sort_order"),
        Index("ix_learning_exam_questions_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    exam_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_exams.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    stem: Mapped[str] = mapped_column(String(500), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class LearningExamAssignment(Base, TimestampMixin):
    """Assignment target of an `assigned`-visibility exam: one employee or one group."""

    __tablename__ = "learning_exam_assignments"
    __table_args__ = (
        UniqueConstraint("exam_id", "target_type", "target_id", name="uq_learning_exam_assign_exam_target"),
        Index("ix_learning_exam_assign_tenant", "tenant_id"),
        Index("ix_learning_exam_assign_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    exam_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_exams.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)


class LearningExamAttempt(Base, TimestampMixin):
    """One exam sitting by an employee: start -> submit (or auto-submit) -> graded.

    The question snapshot is frozen at start time so later question edits never
    rewrite history. Abandoned attempts (left without submitting) neither count
    towards the attempt limit nor appear in score history.
    """

    __tablename__ = "learning_exam_attempts"
    __table_args__ = (
        Index("ix_learning_exam_attempts_exam_employee", "exam_id", "employee_id"),
        Index("ix_learning_exam_attempts_tenant_employee", "tenant_id", "employee_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    exam_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_exams.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ATTEMPT_STATUS_IN_PROGRESS, server_default=ATTEMPT_STATUS_IN_PROGRESS
    )
    attempt_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
