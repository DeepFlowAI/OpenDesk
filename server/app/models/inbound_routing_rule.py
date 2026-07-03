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
    # Where a matched call is routed: an internal voice flow, or a VoiceSpeed agent.
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="voice_flow")
    target_voice_flow_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("voice_flows.id", ondelete="RESTRICT"), nullable=True
    )
    # VoiceSpeed agent reference (id stored as string for forward compatibility)
    # plus a display-name snapshot for "target unavailable" fallback in lists.
    voicespeed_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    voicespeed_agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Single transfer-to-human target for the direct-connect mode,
    # reusing the assign_queue target shape {queue_type, queue_id}.
    transfer_target: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
