"""
Channel model — web/SDK channel configurations for online customer service
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Integer, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("channel_key", name="uq_channels_channel_key"),
        Index("ix_channels_tenant_id", "tenant_id"),
        Index("ix_channels_tenant_type", "tenant_id", "channel_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="web")
    access_mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="url")
    channel_key: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    public_access_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    key_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
