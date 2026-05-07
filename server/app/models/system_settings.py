"""
SystemSettings model — per-tenant system configuration
"""
from sqlalchemy import Boolean, String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class SystemSettings(Base, TimestampMixin):
    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_system_settings_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    default_language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="zh")
    default_timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Shanghai")
    organization_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
