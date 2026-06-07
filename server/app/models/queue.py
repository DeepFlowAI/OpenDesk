"""
Unified queue engine models.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class QueueTask(Base, TimestampMixin):
    __tablename__ = "queue_tasks"
    __table_args__ = (
        Index(
            "ix_queue_tasks_dispatch",
            "tenant_id",
            "channel",
            "queue_type",
            "queue_id",
            "status",
            "priority",
            "enqueued_at",
            "id",
        ),
        Index("ix_queue_tasks_ref", "tenant_id", "task_type", "task_ref_id"),
        Index("ix_queue_tasks_deadline", "tenant_id", "status", "deadline_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    task_ref_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_ref_public_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    queue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    queue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="5")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default="manual_api")
    source_context: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    policy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    assignment_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    assigned_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    assigning_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QueuePolicy(Base, TimestampMixin):
    __tablename__ = "queue_policies"
    __table_args__ = (
        Index("ix_queue_policies_lookup", "tenant_id", "channel", "scope_type", "scope_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    assignment_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_waiting_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_wait_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class QueueRoundRobinState(Base, TimestampMixin):
    __tablename__ = "queue_round_robin_states"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", "queue_type", "queue_id", name="uq_queue_rr_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    queue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    queue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    last_agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    cursor_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class QueueAssignmentEvent(Base):
    __tablename__ = "queue_assignment_events"
    __table_args__ = (
        Index("ix_queue_assignment_events_task", "task_id"),
        Index("ix_queue_assignment_events_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("queue_tasks.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    queue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    queue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    queue_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    before_load: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_load: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class QueueOutboxEvent(Base):
    __tablename__ = "queue_outbox_events"
    __table_args__ = (
        Index("ix_queue_outbox_pending", "status", "next_retry_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
