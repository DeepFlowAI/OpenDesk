"""
Offline message models for Web SDK leave-message mode.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class OfflineMessage(Base, TimestampMixin):
    __tablename__ = "offline_messages"
    __table_args__ = (
        Index("ix_offline_messages_tenant_status", "tenant_id", "status"),
        Index("ix_offline_messages_tenant_last_message", "tenant_id", "last_message_at"),
        Index("ix_offline_messages_tenant_channel_visitor", "tenant_id", "channel_id", "visitor_external_id"),
        Index("ix_offline_messages_target_group", "tenant_id", "target_group_id"),
        Index(
            "ix_offline_messages_customer_unread",
            "tenant_id",
            "channel_id",
            "visitor_external_id",
            "customer_unread_at",
        ),
        Index(
            "uq_offline_messages_pending_visitor",
            "tenant_id",
            "channel_id",
            "visitor_external_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    visitor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    visitor_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    visitor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    handled_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    customer_unread_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_unread_first_message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")

    visitor = relationship("User", lazy="selectin")
    channel = relationship("Channel", lazy="selectin")
    target_group = relationship("EmployeeGroup", lazy="selectin")
    conversation = relationship("Conversation", lazy="selectin")
    handled_by = relationship("Employee", lazy="selectin")
    messages = relationship(
        "OfflineMessageEntry",
        back_populates="offline_message",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="OfflineMessageEntry.id",
    )


class OfflineMessageEntry(Base):
    __tablename__ = "offline_message_entries"
    __table_args__ = (
        Index("ix_offline_message_entries_message_created", "offline_message_id", "created_at"),
        Index("ix_offline_message_entries_tenant_message", "tenant_id", "offline_message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    offline_message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("offline_messages.id", ondelete="CASCADE"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="text")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    offline_message = relationship("OfflineMessage", back_populates="messages")
