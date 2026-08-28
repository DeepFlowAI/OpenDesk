"""
Bulk SMS task models: engagement-center bulk send tasks and their targets.

Tasks snapshot the granted template (name/sign/body/variables/provider binding)
so later platform-side template changes do not affect published tasks.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin

SMS_BULK_TASK_STATUS_DRAFT = "draft"
SMS_BULK_TASK_STATUS_SCHEDULED = "scheduled"
SMS_BULK_TASK_STATUS_SENDING = "sending"
SMS_BULK_TASK_STATUS_PAUSED = "paused"
SMS_BULK_TASK_STATUS_COMPLETED = "completed"
SMS_BULK_TASK_STATUS_ARCHIVED = "archived"

SMS_BULK_SEND_TYPE_IMMEDIATE = "immediate"
SMS_BULK_SEND_TYPE_SCHEDULED = "scheduled"

SMS_BULK_PAUSE_REASON_MANUAL = "manual"
SMS_BULK_PAUSE_REASON_CHANNEL_ERROR = "channel_error"

SMS_BULK_TARGET_STATUS_PENDING = "pending"
SMS_BULK_TARGET_STATUS_SENDING = "sending"
SMS_BULK_TARGET_STATUS_SUBMITTED = "submitted"
SMS_BULK_TARGET_STATUS_DELIVERED = "delivered"
SMS_BULK_TARGET_STATUS_FAILED = "failed"

SMS_BULK_TARGET_TERMINAL_STATUSES = (
    SMS_BULK_TARGET_STATUS_DELIVERED,
    SMS_BULK_TARGET_STATUS_FAILED,
)


class SmsBulkTask(Base, TimestampMixin):
    """A bulk SMS send task with a frozen template snapshot."""

    __tablename__ = "sms_bulk_tasks"
    __table_args__ = (
        Index("ix_sms_bulk_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_sms_bulk_tasks_tenant_updated", "tenant_id", "updated_at"),
        Index("ix_sms_bulk_tasks_tenant_creator", "tenant_id", "created_by_id"),
        Index("ix_sms_bulk_tasks_scheduled", "status", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SMS_BULK_TASK_STATUS_DRAFT, server_default=SMS_BULK_TASK_STATUS_DRAFT
    )
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sms_templates.id", ondelete="SET NULL"), nullable=True
    )
    template_name: Mapped[str] = mapped_column(String(64), nullable=False)
    template_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sign_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_sign_name: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    variables: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    send_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SMS_BULK_SEND_TYPE_IMMEDIATE, server_default=SMS_BULK_SEND_TYPE_IMMEDIATE
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )

    targets: Mapped[list["SmsBulkTarget"]] = relationship(
        "SmsBulkTarget", back_populates="task", cascade="all, delete-orphan"
    )


class SmsBulkTarget(Base, TimestampMixin):
    """One recipient row of a bulk task: phone + per-variable values."""

    __tablename__ = "sms_bulk_targets"
    __table_args__ = (
        UniqueConstraint("task_id", "phone", name="uq_sms_bulk_targets_task_phone"),
        Index("ix_sms_bulk_targets_tenant_task_status", "tenant_id", "task_id", "status"),
        Index("ix_sms_bulk_targets_task_status", "task_id", "status"),
        Index("ix_sms_bulk_targets_send_record", "send_record_id"),
        Index("ix_sms_bulk_targets_provider_biz_id", "provider_biz_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sms_bulk_tasks.id", ondelete="CASCADE"), nullable=False
    )
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    variable_values: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SMS_BULK_TARGET_STATUS_PENDING, server_default=SMS_BULK_TARGET_STATUS_PENDING
    )
    fail_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    send_record_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sms_send_records.id", ondelete="SET NULL"), nullable=True
    )
    provider_biz_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["SmsBulkTask"] = relationship("SmsBulkTask", back_populates="targets")
