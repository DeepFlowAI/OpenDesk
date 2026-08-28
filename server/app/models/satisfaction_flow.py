"""Versioned call satisfaction flow models."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import AuditActorMixin, TimestampMixin


class SatisfactionFlow(Base, TimestampMixin):
    """Tenant-owned satisfaction flow header."""

    __tablename__ = "satisfaction_flows"
    __table_args__ = (Index("ix_satisfaction_flows_tenant_id", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("satisfaction_flow_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    versions: Mapped[list["SatisfactionFlowVersion"]] = relationship(
        "SatisfactionFlowVersion",
        back_populates="flow",
        primaryjoin="SatisfactionFlow.id == SatisfactionFlowVersion.satisfaction_flow_id",
        foreign_keys="SatisfactionFlowVersion.satisfaction_flow_id",
        lazy="noload",
    )
    current_version: Mapped["SatisfactionFlowVersion | None"] = relationship(
        "SatisfactionFlowVersion",
        primaryjoin="SatisfactionFlow.current_version_id == SatisfactionFlowVersion.id",
        foreign_keys=[current_version_id],
        post_update=True,
        lazy="joined",
    )


class SatisfactionFlowVersion(Base, TimestampMixin, AuditActorMixin):
    """Immutable snapshot created on every flow save or rollback."""

    __tablename__ = "satisfaction_flow_versions"
    __table_args__ = (
        UniqueConstraint(
            "satisfaction_flow_id", "version_no", name="uq_sfv_flow_version"
        ),
        Index("ix_sfv_tenant_flow", "tenant_id", "satisfaction_flow_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    satisfaction_flow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("satisfaction_flows.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    description_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    graph_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment: Mapped[str | None] = mapped_column(String(200), nullable=True)

    flow: Mapped[SatisfactionFlow] = relationship(
        SatisfactionFlow,
        back_populates="versions",
        primaryjoin="SatisfactionFlowVersion.satisfaction_flow_id == SatisfactionFlow.id",
        foreign_keys=[satisfaction_flow_id],
    )
