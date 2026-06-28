"""
OpenAgentSettings model — per-tenant OpenAgent connection configuration.
"""
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class OpenAgentSettings(Base, TimestampMixin):
    __tablename__ = "open_agent_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_open_agent_settings_tenant"),
        Index("ix_open_agent_settings_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_speed_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    voice_speed_api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
