"""
Message model — individual messages within a conversation
"""
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index, func, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.enums import MessageSenderType, MessageContentType


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_tenant_conversation", "tenant_id", "conversation_id"),
        Index("ix_messages_conversation_visitor_read", "conversation_id", "visitor_read_at"),
        Index("ix_messages_conversation_agent_read", "conversation_id", "agent_read_at"),
        Index("ix_messages_recalled", "is_recalled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MessageContentType.TEXT.value, server_default="text"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_recalled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    recalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recalled_by_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    recalled_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recalled_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    visitor_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agent_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
