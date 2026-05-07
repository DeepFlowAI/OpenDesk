"""
ServiceHours model — configurable weekly/holiday/makeup-day service hour sets
"""
from sqlalchemy import String, Text, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ServiceHours(Base, TimestampMixin):
    __tablename__ = "service_hours"
    __table_args__ = (
        Index("ix_service_hours_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_schedules: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    holidays: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    makeup_days: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
