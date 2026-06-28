"""
Per-conversation, per-queue waiting summary.

One row per ``(conversation_id, queue_type, queue_id)``. Materialized by the
queue engine so that queue reports and session records can read queue metrics
without re-aggregating ``queue_tasks`` at query time.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationQueueSummary(Base, TimestampMixin):
    __tablename__ = "conversation_queue_summaries"
    __table_args__ = (
        UniqueConstraint("conversation_id", "queue_type", "queue_id", name="uq_conv_queue_summary"),
        Index("ix_conv_queue_summary_queue", "tenant_id", "queue_type", "queue_id"),
        Index("ix_conv_queue_summary_started", "tenant_id", "conversation_started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    queue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    queue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    queue_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wait_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_last_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Final result of this queue's latest substantial task: assigned / canceled /
    # timeout, NULL when the queue had no substantial wait.
    queue_result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    conversation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
