"""
VoiceFlow — minimal IVR flow record for routing rule targets (full editor in 1.6.2)
"""
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class VoiceFlow(Base, TimestampMixin):
    __tablename__ = "voice_flows"
    __table_args__ = (Index("ix_voice_flows_tenant_id", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
