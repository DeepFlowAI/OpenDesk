"""
Auto outbound task models.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class AutoOutboundTask(Base, TimestampMixin):
    __tablename__ = "auto_outbound_tasks"
    __table_args__ = (
        Index("ix_auto_outbound_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_auto_outbound_tasks_tenant_updated", "tenant_id", "updated_at"),
        Index("ix_auto_outbound_tasks_tenant_creator", "tenant_id", "created_by_id"),
        Index("ix_auto_outbound_tasks_tenant_mode", "tenant_id", "execution_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("outbound_task_templates.id", ondelete="SET NULL"), nullable=True
    )
    template_name: Mapped[str] = mapped_column(String(80), nullable=False)
    fields: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="draft")
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False)

    # Reception configuration
    voice_flow_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voice_flow_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transfer_queue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voicespeed_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    voicespeed_agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    intent_result_field_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    queue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pacing_mode: Mapped[str | None] = mapped_column(String(24), nullable=True)
    dial_ratio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dial_intensity: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    abandon_rate_limit: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    abandon_prompt: Mapped[str | None] = mapped_column(String(24), nullable=True)
    wrapup_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")

    # Schedule
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    daily_time_windows: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    caller_number_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("phone_numbers.id", ondelete="SET NULL"), nullable=True
    )

    # Dial strategy
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    retry_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    daily_per_number_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    auto_resume_on_target_append: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    auto_pause_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    targets: Mapped[list["AutoOutboundTarget"]] = relationship(
        "AutoOutboundTarget", back_populates="task", cascade="all, delete-orphan"
    )


class AutoOutboundTarget(Base, TimestampMixin):
    __tablename__ = "auto_outbound_targets"
    __table_args__ = (
        Index("ix_auto_outbound_targets_task_id", "task_id"),
        Index("ix_auto_outbound_targets_phone_number", "phone_number"),
        Index("ix_auto_outbound_targets_status", "status"),
        Index("ix_auto_outbound_targets_next_call_at", "next_call_at"),
        Index("ix_auto_outbound_targets_task_status_next", "task_id", "status", "next_call_at"),
        Index("ix_auto_outbound_targets_tenant_task", "tenant_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("auto_outbound_tasks.id", ondelete="CASCADE"), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    field_values: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    answered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    retry_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    last_called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_call_result: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["AutoOutboundTask"] = relationship("AutoOutboundTask", back_populates="targets")


class AutoOutboundCallRecord(Base, TimestampMixin):
    __tablename__ = "auto_outbound_call_records"
    __table_args__ = (
        Index("ix_auto_outbound_records_task_id", "task_id"),
        Index("ix_auto_outbound_records_tenant_task_started", "tenant_id", "task_id", "started_at"),
        Index("ix_auto_outbound_records_tenant_target_started", "tenant_id", "target_id", "started_at"),
        Index(
            "uq_auto_outbound_records_attempt_id",
            "attempt_id",
            unique=True,
            postgresql_where=text("attempt_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("auto_outbound_tasks.id", ondelete="CASCADE"), nullable=False)
    target_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("auto_outbound_targets.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="SET NULL"), nullable=True
    )
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    terminal_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reception_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    reception_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
