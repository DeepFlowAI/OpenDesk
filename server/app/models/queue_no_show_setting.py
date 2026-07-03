"""
Queue no-show cancel configuration.

Tenant-level toggle: when enabled, a queued online-chat task whose Web SDK
visitor is offline at auto-assignment time is canceled instead of assigned.
"""
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class QueueNoShowSetting(Base, TimestampMixin):
    __tablename__ = "queue_no_show_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_queue_no_show_settings_tenant_id"),
        Index("ix_queue_no_show_settings_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    updated_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
