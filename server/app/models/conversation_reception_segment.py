"""
Per-conversation reception segment.

One row per continuous period during which a single agent was responsible for a
conversation. Generated in bulk after the conversation ends from the structured
reception events plus the message timeline, then self-validated. Maintained with
the same "one conversation, many rows + materialized columns on conversations +
idempotent replace" pattern as ``conversation_queue_summaries``.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationReceptionSegment(Base, TimestampMixin):
    __tablename__ = "conversation_reception_segments"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq_no", name="uq_reception_segment_seq"),
        Index(
            "ix_reception_segment_tenant_agent",
            "tenant_id",
            "agent_id",
            "conversation_started_at",
        ),
        Index("ix_reception_segment_conversation", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    agent_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True
    )
    group_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entry_reason: Mapped[str] = mapped_column(String(24), nullable=False)
    end_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    from_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    to_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    visitor_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    agent_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    first_response_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_response_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
