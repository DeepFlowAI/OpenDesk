"""Durable employee participation facts projected from call events."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class CallAgentReceptionSegment(Base, TimestampMixin):
    """One continuous period of customer responsibility for one employee."""

    __tablename__ = "call_agent_reception_segments"
    __table_args__ = (
        UniqueConstraint("started_event_id", name="uq_call_agent_segments_started_event"),
        UniqueConstraint(
            "call_record_id", "segment_ordinal", name="uq_call_agent_segments_call_ordinal"
        ),
        Index("ix_call_agent_segments_report", "tenant_id", "agent_id", "started_at"),
        Index("ix_call_agent_segments_call", "call_record_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    started_event_id: Mapped[str] = mapped_column(String(96), nullable=False)
    ended_event_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    segment_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_reason: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown"
    )
    end_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    talk_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    hold_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    consult_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    held: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    result_reliable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class CallAgentOperation(Base, TimestampMixin):
    """One transfer, consultation, or conference operation by an employee."""

    __tablename__ = "call_agent_operations"
    __table_args__ = (
        UniqueConstraint(
            "call_record_id",
            "operation_key",
            "operation_type",
            "actor_agent_id",
            name="uq_call_agent_operations_identity",
        ),
        Index("ix_call_agent_operations_report", "tenant_id", "actor_agent_id", "started_at"),
        Index("ix_call_agent_operations_call", "call_record_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_event_id: Mapped[str] = mapped_column(String(96), nullable=False)
    ended_event_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(String(24), nullable=True)
    result_reliable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class CallAgentAfterCallWork(Base, TimestampMixin):
    """Actual after-call work interval associated with an employee and call."""

    __tablename__ = "call_agent_after_call_work"
    __table_args__ = (
        UniqueConstraint("call_record_id", "agent_id", name="uq_call_agent_acw_call_agent"),
        Index("ix_call_agent_acw_report", "tenant_id", "agent_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    reception_segment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("call_agent_reception_segments.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_reliable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
