"""
AgentWebRTCSession — bridges OpenDesk's `employee_id` to the FlowKit-side
WebRTC leg `call_id`. One active row per employee; closed rows kept for
audit.

A partial-unique index on (tenant_id, employee_id) WHERE state != 'disconnected'
prevents accidental double-registration.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AgentWebRTCSession(Base):
    __tablename__ = "agent_webrtc_sessions"
    __table_args__ = (
        Index("ix_aws_tenant_employee_state", "tenant_id", "employee_id", "state"),
        Index(
            "uq_aws_active_per_employee",
            "tenant_id",
            "employee_id",
            unique=True,
            postgresql_where=text("state <> 'disconnected'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    webrtc_call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
