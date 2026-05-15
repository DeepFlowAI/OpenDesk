"""
Tenant model
"""
from sqlalchemy import String, Boolean, Text, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    __table_args__ = (
        Index(
            "uq_tenants_slug_not_null",
            "slug",
            unique=True,
            postgresql_where=text("slug IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    employees: Mapped[list["Employee"]] = relationship("Employee", back_populates="tenant", cascade="all, delete-orphan")
