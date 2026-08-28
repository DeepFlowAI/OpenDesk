"""Custom dashboard models for tenant-owned draft and published snapshots."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class CustomDashboard(Base, TimestampMixin):
    """Tenant-owned dashboard lifecycle header."""

    __tablename__ = "custom_dashboards"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_custom_dashboards_tenant_name"),
        UniqueConstraint("tenant_id", "slug", name="uq_custom_dashboards_tenant_slug"),
        CheckConstraint(
            "status IN ('draft', 'published', 'disabled')",
            name="ck_custom_dashboards_status",
        ),
        Index(
            "ix_custom_dashboards_tenant_status_sort",
            "tenant_id",
            "status",
            "sort_order",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["CustomDashboardVersion"]] = relationship(
        "CustomDashboardVersion",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class CustomDashboardVersion(Base, TimestampMixin):
    """Mutable current draft or published snapshot for a dashboard."""

    __tablename__ = "custom_dashboard_versions"
    __table_args__ = (
        UniqueConstraint("dashboard_id", "kind", name="uq_custom_dashboard_versions_kind"),
        CheckConstraint(
            "kind IN ('draft', 'published')",
            name="ck_custom_dashboard_versions_kind",
        ),
        Index(
            "ix_custom_dashboard_versions_tenant_dashboard",
            "tenant_id",
            "dashboard_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    dashboard_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("custom_dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    icon: Mapped[str] = mapped_column(
        String(64), nullable=False, default="chart-bar", server_default="chart-bar"
    )
    filters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    components: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    dashboard: Mapped[CustomDashboard] = relationship(
        "CustomDashboard",
        back_populates="versions",
    )
