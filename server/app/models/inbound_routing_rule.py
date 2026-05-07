"""
InboundRoutingRule — call routing rules (priority order, JSON conditions)
"""
from sqlalchemy import String, Integer, ForeignKey, Boolean, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class InboundRoutingRule(Base, TimestampMixin):
    __tablename__ = "inbound_routing_rules"
    __table_args__ = (
        Index("ix_inbound_routing_rules_tenant_id", "tenant_id"),
        Index("ix_inbound_routing_rules_tenant_priority", "tenant_id", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    target_voice_flow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("voice_flows.id", ondelete="RESTRICT"), nullable=False
    )
