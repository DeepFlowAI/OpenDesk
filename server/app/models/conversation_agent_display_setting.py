"""
Conversation agent display-name configuration.
"""
from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationAgentDisplaySetting(Base, TimestampMixin):
    __tablename__ = "conversation_agent_display_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_conversation_agent_display_settings_tenant_id"),
        Index("ix_conversation_agent_display_settings_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    display_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="name", server_default="name")
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
