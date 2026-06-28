"""
Conversation pin model.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationPin(Base, TimestampMixin):
    __tablename__ = "conversation_pins"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_id",
            "conversation_id",
            name="uq_conversation_pins_agent_conversation",
        ),
        Index("ix_conversation_pins_agent_pinned_at", "tenant_id", "agent_id", "pinned_at"),
        Index("ix_conversation_pins_conversation", "tenant_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    pinned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
