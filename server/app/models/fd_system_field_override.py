"""
FdSystemFieldOverride — per-tenant overrides for hardcoded system fields.

System field definitions live in app.constants.system_fields (code-only).
This table stores only the tenant-specific display preferences:
show_in_workspace, sort_order, status.
"""
from sqlalchemy import Boolean, Integer, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class FdSystemFieldOverride(Base, TimestampMixin):
    __tablename__ = "fd_system_field_overrides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", "field_key", name="uq_sys_override_tenant_domain_key"),
        Index("ix_sys_override_tenant_domain", "tenant_id", "domain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    show_in_workspace: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
