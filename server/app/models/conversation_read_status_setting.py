"""
Read-status display settings for Web conversations.
"""
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationReadStatusSetting(Base, TimestampMixin):
    __tablename__ = "conversation_read_status_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_conversation_read_status_settings_tenant_id"),
        Index("ix_conversation_read_status_settings_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    agent_workspace_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    web_sdk_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
