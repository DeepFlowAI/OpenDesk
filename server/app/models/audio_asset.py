"""
AudioAsset — uploaded mp3/wav prompts referenced by voice flow graph nodes
(play / collect / hangup). Not FK-linked to graph_json — schema layer enforces
existence; soft-delete keeps history versions intact.
"""
from datetime import datetime

from sqlalchemy import BigInteger, Integer, String, ForeignKey, Index, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin, AuditActorMixin


class AudioAsset(Base, TimestampMixin, AuditActorMixin):
    __tablename__ = "audio_assets"
    __table_args__ = (Index("ix_audio_assets_tenant", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
