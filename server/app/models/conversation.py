"""
Conversation model — a chat session between an end user and an agent
"""
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin
from app.enums import ConversationStatus


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_conversations_public_id"),
        UniqueConstraint("share_code", name="uq_conversations_share_code"),
        Index("ix_conversations_tenant_agent_status", "tenant_id", "agent_id", "status"),
        Index("ix_conversations_tenant_status", "tenant_id", "status"),
        Index("ix_conversations_tenant_visitor", "tenant_id", "visitor_id"),
        Index("ix_conversations_last_message_at", "last_message_at"),
        Index("ix_conversations_tenant_started_at", "tenant_id", "started_at"),
        Index("ix_conversations_channel_id", "channel_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    share_code: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    visitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ConversationStatus.QUEUED.value, server_default="queued"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    visitor: Mapped["User"] = relationship("User", lazy="selectin")
    agent: Mapped["Employee | None"] = relationship("Employee", lazy="selectin")
    channel: Mapped["Channel | None"] = relationship("Channel", lazy="selectin")
    group: Mapped["EmployeeGroup | None"] = relationship("EmployeeGroup", lazy="selectin")
