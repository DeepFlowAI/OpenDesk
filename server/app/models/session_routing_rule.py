"""
SessionRoutingRule — online service session routing rules (priority order, JSON conditions)
"""
from sqlalchemy import String, Integer, ForeignKey, Boolean, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class SessionRoutingRule(Base, TimestampMixin):
    __tablename__ = "session_routing_rules"
    __table_args__ = (
        Index("ix_session_routing_rules_tenant_id", "tenant_id"),
        Index("ix_session_routing_rules_tenant_priority", "tenant_id", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    target_group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="RESTRICT"), nullable=False
    )
