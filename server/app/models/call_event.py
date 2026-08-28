"""Append-only structured events for a call trajectory."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CallEvent(Base):
    """A single immutable business or media event in a call trajectory."""

    __tablename__ = "call_events"
    __table_args__ = (
        Index("uq_call_events_event_id", "event_id", unique=True),
        Index("uq_call_events_sequence", "call_record_id", "sequence_no", unique=True),
        Index(
            "uq_call_events_source_event",
            "source",
            "source_event_id",
            unique=True,
            postgresql_where=text("source_event_id IS NOT NULL"),
        ),
        Index(
            "ix_call_events_timeline",
            "call_record_id",
            "occurred_at",
            "sequence_no",
            "id",
        ),
        Index("ix_call_events_root", "tenant_id", "root_call_id"),
        Index("ix_call_events_operation", "call_record_id", "operation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(96), nullable=False)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    root_call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_category: Mapped[str] = mapped_column(String(24), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)

    operation_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    call_leg_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    parent_leg_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    participant_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    queue_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    queue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str | None] = mapped_column(String(24), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    reason_detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
