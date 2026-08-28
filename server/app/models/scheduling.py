"""
Scheduling Center models: shift templates and schedule assignments.
"""
from datetime import date, datetime, time

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ScheduleShift(Base, TimestampMixin):
    """Reusable shift template within a tenant (name, time range, color).

    ``end_time < start_time`` means an overnight shift; the assignment belongs
    to the calendar day it starts on. ``end_time == start_time`` is rejected
    at the service layer (zero-length shift).
    """

    __tablename__ = "schedule_shifts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_schedule_shifts_tenant_name"),
        Index("ix_schedule_shifts_tenant_id", "tenant_id"),
        CheckConstraint(
            "shift_type IN ('work', 'leave')",
            name="ck_schedule_shifts_shift_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    shift_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="work"
    )
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    color: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ScheduleAssignment(Base, TimestampMixin):
    """One employee assigned to one shift on one calendar date."""

    __tablename__ = "schedule_assignments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "employee_id", "shift_id", "date",
            name="uq_schedule_assignments_emp_shift_date",
        ),
        Index("ix_schedule_assignments_tenant_date", "tenant_id", "date"),
        Index("ix_schedule_assignments_tenant_shift", "tenant_id", "shift_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    shift_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedule_shifts.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)


class SchedulePublishedSnapshot(Base, TimestampMixin):
    """Published snapshot of one calendar week's assignments within a tenant.

    Publishing freezes the current week (Monday-Sunday) into ``payload`` so the
    board can later be reset to this version. Re-publishing overwrites the row;
    only the latest snapshot per tenant+week is kept. ``payload`` entries are
    ``{"shift_id", "employee_id", "date"}`` dicts sorted deterministically.
    """

    __tablename__ = "schedule_published_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "week_start", name="uq_schedule_published_tenant_week"),
        Index("ix_schedule_published_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    published_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
