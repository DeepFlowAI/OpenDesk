"""
Employee model — help desk employees / admins
"""
from datetime import datetime

from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_employees_tenant_username"),
        Index("ix_employees_tenant_email", "tenant_id", "email"),
        Index("ix_employees_tenant_job_number", "tenant_id", "job_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    roles: Mapped[list] = mapped_column(JSON, nullable=False, server_default='["agent"]')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    name: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(512), nullable=True)
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    default_language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="system")
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="employees")
