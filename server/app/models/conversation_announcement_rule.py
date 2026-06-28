"""
ConversationAnnouncementRule — visitor chat announcement rules.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationAnnouncementRule(Base, TimestampMixin):
    __tablename__ = "conversation_announcement_rules"
    __table_args__ = (
        Index("ix_conversation_announcement_rules_tenant_id", "tenant_id"),
        Index("ix_conversation_announcement_rules_tenant_priority", "tenant_id", "priority"),
        Index("ix_conversation_announcement_rules_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    time_range_type: Mapped[str] = mapped_column(String(16), nullable=False, default="permanent", server_default="permanent")
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    auto_popup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    background_color: Mapped[str] = mapped_column(String(16), nullable=False, default="yellow", server_default="yellow")
    summary_html: Mapped[str] = mapped_column(Text, nullable=False)
    detail_html: Mapped[str] = mapped_column(Text, nullable=False)
