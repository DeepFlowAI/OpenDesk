"""
Structured reception event — an append-only record of a responsibility change
within a single customer conversation.

Logged at runtime whenever the responsible agent changes (first human takeover,
bot-to-human handoff, transfer, admin reassign) or the conversation ends. Unlike
the human-readable system messages (which only carry agent *names*), these
events store the agent *id*, so the post-end reception-segment generation can
reliably attribute each segment to a specific agent.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationReceptionEvent(Base, TimestampMixin):
    __tablename__ = "conversation_reception_events"
    __table_args__ = (
        Index(
            "ix_reception_events_conversation",
            "conversation_id",
            "occurred_at",
            "id",
        ),
        Index("ix_reception_events_tenant_agent", "tenant_id", "agent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True
    )
    from_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    to_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
