"""
Satisfaction survey configuration and immutable published versions.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class SatisfactionSurveyConfig(Base, TimestampMixin):
    __tablename__ = "satisfaction_survey_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_satisfaction_survey_configs_tenant_id"),
        Index("ix_satisfaction_survey_configs_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    triggers: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    service_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    product_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)


class SatisfactionSurveyConfigVersion(Base, TimestampMixin):
    __tablename__ = "satisfaction_survey_config_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_satisfaction_survey_versions_tenant_version"),
        Index("ix_satisfaction_survey_versions_tenant_published", "tenant_id", "published_at"),
        Index("ix_satisfaction_survey_versions_config_version", "config_id", "version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("satisfaction_survey_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
