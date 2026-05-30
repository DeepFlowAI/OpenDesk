"""
VoiceFlowVersion — each save of a voice flow graph produces a new version row.

voice_flows.current_version_id points to the active one. Rollback = copy old
graph_json into a new version row, then update current_version_id.
"""
from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin, AuditActorMixin


class VoiceFlowVersion(Base, TimestampMixin, AuditActorMixin):
    __tablename__ = "voice_flow_versions"
    __table_args__ = (
        UniqueConstraint("voice_flow_id", "version_no", name="uq_vfv_flow_version"),
        Index("ix_vfv_tenant_flow", "tenant_id", "voice_flow_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    voice_flow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("voice_flows.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(200), nullable=True)

    voice_flow: Mapped["VoiceFlow"] = relationship(  # noqa: F821
        "VoiceFlow",
        back_populates="versions",
        foreign_keys=[voice_flow_id],
    )
