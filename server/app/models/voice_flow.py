"""
VoiceFlow — IVR flow header. Graph (nodes + edges) lives in
voice_flow_versions; current_version_id points to the active version.
"""
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class VoiceFlow(Base, TimestampMixin):
    __tablename__ = "voice_flows"
    __table_args__ = (Index("ix_voice_flows_tenant_id", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Pointer to the active version row. Nullable until the first version is created.
    # ondelete="SET NULL" so dropping a version row never cascades into deleting the flow.
    current_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("voice_flow_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    versions: Mapped[list["VoiceFlowVersion"]] = relationship(  # noqa: F821
        "VoiceFlowVersion",
        back_populates="voice_flow",
        primaryjoin="VoiceFlow.id == VoiceFlowVersion.voice_flow_id",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    current_version: Mapped["VoiceFlowVersion | None"] = relationship(  # noqa: F821
        "VoiceFlowVersion",
        primaryjoin="VoiceFlow.current_version_id == VoiceFlowVersion.id",
        foreign_keys=[current_version_id],
        post_update=True,
        lazy="joined",
    )
