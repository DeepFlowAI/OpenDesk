"""
Manual outbound task models.
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class OutboundTaskTemplate(Base, TimestampMixin):
    __tablename__ = "outbound_task_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_outbound_task_templates_tenant_name"),
        Index("ix_outbound_task_templates_tenant_updated", "tenant_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    script: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)

    @property
    def has_script(self) -> bool:
        return self.script is not None


class OutboundTask(Base, TimestampMixin):
    __tablename__ = "outbound_tasks"
    __table_args__ = (
        Index("ix_outbound_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_outbound_tasks_tenant_updated", "tenant_id", "updated_at"),
        Index("ix_outbound_tasks_tenant_creator", "tenant_id", "created_by_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("outbound_task_templates.id", ondelete="SET NULL"), nullable=True)
    template_name: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="draft")
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allow_self_claim: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    default_redial_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignment_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="manual")
    assignee_scope_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    fields: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    script_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    template: Mapped["OutboundTaskTemplate | None"] = relationship("OutboundTaskTemplate")
    targets: Mapped[list["OutboundTaskTarget"]] = relationship("OutboundTaskTarget", back_populates="task", cascade="all, delete-orphan")

    @property
    def has_script(self) -> bool:
        return self.script_snapshot is not None


class OutboundTaskTarget(Base, TimestampMixin):
    __tablename__ = "outbound_task_targets"
    __table_args__ = (
        Index("ix_outbound_targets_tenant_task_status", "tenant_id", "task_id", "status"),
        Index("ix_outbound_targets_tenant_assignee_status", "tenant_id", "assignee_id", "status"),
        Index("ix_outbound_targets_tenant_phone", "tenant_id", "phone_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("outbound_tasks.id", ondelete="CASCADE"), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assignee_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    field_values: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    answered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_call_result: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_talk_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    task: Mapped["OutboundTask"] = relationship("OutboundTask", back_populates="targets")


class OutboundCallRecord(Base, TimestampMixin):
    __tablename__ = "outbound_call_records"
    __table_args__ = (
        Index("ix_outbound_records_tenant_task_started", "tenant_id", "task_id", "started_at"),
        Index("ix_outbound_records_tenant_target_started", "tenant_id", "target_id", "started_at"),
        Index("ix_outbound_records_tenant_agent_started", "tenant_id", "agent_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("outbound_tasks.id", ondelete="CASCADE"), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, ForeignKey("outbound_task_targets.id", ondelete="CASCADE"), nullable=False)
    call_record_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("call_records.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    result: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_values: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
