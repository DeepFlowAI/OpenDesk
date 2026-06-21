"""
CallRecord — CDR (call detail record) for every voice call handled by the
call center. Written by the orchestrator across the call lifecycle.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class CallRecord(Base, TimestampMixin):
    __tablename__ = "call_records"
    __table_args__ = (
        Index("ix_cr_tenant_started", "tenant_id", "started_at"),
        Index("ix_cr_tenant_agent", "tenant_id", "agent_id"),
        Index("ix_cr_tenant_user", "tenant_id", "user_id"),
        Index("ix_cr_tenant_state", "tenant_id", "state"),
        Index("ix_cr_conversation", "conversation_id"),
        Index("uq_cr_call_id", "call_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    root_call_id: Mapped[str | None] = mapped_column(String(80), nullable=True)

    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)

    from_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    voice_flow_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("voice_flows.id", ondelete="SET NULL"), nullable=True
    )
    voice_flow_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("voice_flow_versions.id", ondelete="SET NULL"), nullable=True
    )
    employee_group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ring_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    talk_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    hangup_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recording_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Extensible payload — IVR DTMF history, TTS transcript, AI summary, etc.
    extra_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
