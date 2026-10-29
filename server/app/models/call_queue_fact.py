"""Query-oriented queue visit and offer facts derived from call events."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class CallQueueVisit(Base, TimestampMixin):
    """One complete or in-progress visit to a call-center queue."""

    __tablename__ = "call_queue_visits"
    __table_args__ = (
        UniqueConstraint("entered_event_id", name="uq_call_queue_visits_entered_event"),
        UniqueConstraint(
            "call_record_id", "visit_ordinal", name="uq_call_queue_visits_call_ordinal"
        ),
        Index(
            "ix_call_queue_visits_report",
            "tenant_id",
            "queue_type",
            "queue_id",
            "entered_at",
        ),
        Index("ix_call_queue_visits_call", "call_record_id", "entered_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    entered_event_id: Mapped[str] = mapped_column(String(96), nullable=False)
    exited_event_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    visit_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    queue_type: Mapped[str] = mapped_column(String(24), nullable=False)
    queue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    queue_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entry_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown", server_default="unknown"
    )
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wait_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    result: Mapped[str | None] = mapped_column(String(24), nullable=True)
    result_reliable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_short_abandon: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class CallQueueOffer(Base, TimestampMixin):
    """One agent-ringing attempt made during a queue visit."""

    __tablename__ = "call_queue_offers"
    __table_args__ = (
        UniqueConstraint("started_event_id", name="uq_call_queue_offers_started_event"),
        Index("ix_call_queue_offers_visit", "queue_visit_id", "started_at"),
        Index("ix_call_queue_offers_tenant_started", "tenant_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    queue_visit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_queue_visits.id", ondelete="CASCADE"), nullable=False
    )
    started_event_id: Mapped[str] = mapped_column(String(96), nullable=False)
    ended_event_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    operation_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    agent_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    result: Mapped[str | None] = mapped_column(String(24), nullable=True)
    result_reliable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
