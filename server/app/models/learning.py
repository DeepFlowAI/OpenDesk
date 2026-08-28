"""
Learning center domain models: courses, sections, materials, assignment targets
and per-employee material learning records.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin

COURSE_STATUS_DRAFT = "draft"
COURSE_STATUS_PUBLISHED = "published"
COURSE_STATUS_UNPUBLISHED = "unpublished"
COURSE_STATUSES = {COURSE_STATUS_DRAFT, COURSE_STATUS_PUBLISHED, COURSE_STATUS_UNPUBLISHED}

VISIBILITY_ALL = "all"
VISIBILITY_ASSIGNED = "assigned"
VISIBILITIES = {VISIBILITY_ALL, VISIBILITY_ASSIGNED}

MATERIAL_TYPE_VIDEO = "video"
MATERIAL_TYPE_AUDIO = "audio"
MATERIAL_TYPE_PDF = "pdf"
MATERIAL_TYPE_DOCUMENT = "document"
MATERIAL_TYPES = {
    MATERIAL_TYPE_VIDEO,
    MATERIAL_TYPE_AUDIO,
    MATERIAL_TYPE_PDF,
    MATERIAL_TYPE_DOCUMENT,
}

TRANSCODE_PROCESSING = "processing"
TRANSCODE_OK = "ok"
TRANSCODE_FAILED = "failed"

ASSIGNMENT_TARGET_EMPLOYEE = "employee"
ASSIGNMENT_TARGET_GROUP = "group"
ASSIGNMENT_TARGET_TYPES = {ASSIGNMENT_TARGET_EMPLOYEE, ASSIGNMENT_TARGET_GROUP}

RECORD_STATUS_IN_PROGRESS = "in_progress"
RECORD_STATUS_COMPLETED = "completed"


class LearningCourse(Base, TimestampMixin):
    """A training course owned by a tenant."""

    __tablename__ = "learning_courses"
    __table_args__ = (
        Index("ix_learning_courses_tenant_status", "tenant_id", "status"),
        Index("ix_learning_courses_tenant_updated", "tenant_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    intro: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=COURSE_STATUS_DRAFT, server_default=COURSE_STATUS_DRAFT
    )
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VISIBILITY_ASSIGNED, server_default=VISIBILITY_ASSIGNED
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )


class LearningSection(Base, TimestampMixin):
    """A first-level chapter inside a course (no nesting)."""

    __tablename__ = "learning_sections"
    __table_args__ = (
        Index("ix_learning_sections_course_sort", "course_id", "sort_order"),
        Index("ix_learning_sections_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class LearningMaterial(Base, TimestampMixin):
    """The smallest learning unit inside a section: video / audio / PDF / office file."""

    __tablename__ = "learning_materials"
    __table_args__ = (
        Index("ix_learning_materials_section_sort", "section_id", "sort_order"),
        Index("ix_learning_materials_course", "course_id"),
        Index("ix_learning_materials_tenant", "tenant_id"),
        Index("ix_learning_materials_vod_video_id", "vod_video_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vod_video_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transcode_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class LearningCourseAssignment(Base, TimestampMixin):
    """Assignment target of an `assigned`-visibility course: one employee or one group."""

    __tablename__ = "learning_course_assignments"
    __table_args__ = (
        UniqueConstraint("course_id", "target_type", "target_id", name="uq_learning_assignments_course_target"),
        Index("ix_learning_assignments_tenant", "tenant_id"),
        Index("ix_learning_assignments_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)


class LearningMaterialRecord(Base, TimestampMixin):
    """Per-employee progress row for one material (no row means not started)."""

    __tablename__ = "learning_material_records"
    __table_args__ = (
        UniqueConstraint("material_id", "employee_id", name="uq_learning_records_material_employee"),
        Index("ix_learning_records_course_employee", "course_id", "employee_id"),
        Index("ix_learning_records_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_learning_records_employee_learned", "employee_id", "last_learn_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("learning_materials.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RECORD_STATUS_IN_PROGRESS, server_default=RECORD_STATUS_IN_PROGRESS
    )
    play_position_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_learn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
