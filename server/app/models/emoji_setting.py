"""
Emoji panel settings for visitor and agent chat composers.
"""
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class EmojiSetting(Base, TimestampMixin):
    __tablename__ = "emoji_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_emoji_settings_tenant_id"),
        Index("ix_emoji_settings_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    agent_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    user_emojis: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    agent_emojis: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
