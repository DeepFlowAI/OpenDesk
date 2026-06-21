"""
Tenant-level display settings for workspace user statistics.
"""
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationUserStatSetting(Base, TimestampMixin):
    __tablename__ = "conversation_user_stat_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_conversation_user_stat_settings_tenant_id"),
        Index("ix_conversation_user_stat_settings_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    show_session_count: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_call_count: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_unresolved_ticket_count: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_total_ticket_count: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
