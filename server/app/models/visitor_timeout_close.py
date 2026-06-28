"""
Visitor timeout auto-close configuration and runtime state.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class VisitorTimeoutCloseSetting(Base, TimestampMixin):
    __tablename__ = "visitor_timeout_close_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_visitor_timeout_close_settings_tenant_id"),
        Index("ix_visitor_timeout_close_settings_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    first_normal_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=110, server_default="110")
    close_normal_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120, server_default="120")
    vip_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    first_vip_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=110, server_default="110")
    close_vip_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120, server_default="120")
    first_reminder_content: Mapped[str] = mapped_column(Text, nullable=False)
    close_reminder_content: Mapped[str] = mapped_column(Text, nullable=False)
    notify_agent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    notify_visitor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)


class VisitorTimeoutCloseState(Base, TimestampMixin):
    __tablename__ = "visitor_timeout_close_states"
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_visitor_timeout_close_states_conversation_id"),
        Index("ix_visitor_timeout_close_states_tenant_next_check", "tenant_id", "next_check_at"),
        Index("ix_visitor_timeout_close_states_tenant_conversation", "tenant_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    anchor_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    anchor_message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    first_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_locked_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
