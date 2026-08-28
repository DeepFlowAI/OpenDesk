"""Personal auto-outbound recordings, sessions, and per-call state."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class PersonalOutboundRecording(Base, TimestampMixin):
    __tablename__ = "personal_outbound_recordings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", "recording_type", name="uq_personal_outbound_recording_owner_type"),
        Index("ix_personal_outbound_recordings_owner", "tenant_id", "employee_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    recording_type: Mapped[str] = mapped_column(String(16), nullable=False)
    audio_asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("audio_assets.id", ondelete="RESTRICT"), nullable=False)
    script_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class PersonalAutoOutboundSession(Base, TimestampMixin):
    __tablename__ = "personal_auto_outbound_sessions"
    __table_args__ = (
        Index("ix_personal_auto_outbound_sessions_owner", "tenant_id", "primary_agent_id", "created_at"),
        Index("ix_personal_auto_outbound_sessions_status", "tenant_id", "status"),
        Index(
            "uq_personal_auto_outbound_active_owner",
            "tenant_id",
            "primary_agent_id",
            unique=True,
            postgresql_where=text("status IN ('running', 'paused', 'auto_paused', 'stopping')"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    primary_agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("outbound_tasks.id", ondelete="RESTRICT"), nullable=False)
    outbound_phone_number_id: Mapped[str] = mapped_column(String(32), ForeignKey("phone_numbers.id", ondelete="RESTRICT"), nullable=False)
    fallback_group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True)
    opening_audio_asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("audio_assets.id", ondelete="RESTRICT"), nullable=False)
    closing_audio_asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("audio_assets.id", ondelete="RESTRICT"), nullable=False)
    opening_script_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    configured_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="4")
    effective_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="running")
    pause_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    intent_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PersonalAutoOutboundCall(Base, TimestampMixin):
    __tablename__ = "personal_auto_outbound_calls"
    __table_args__ = (
        UniqueConstraint("session_id", "target_id", name="uq_personal_auto_outbound_call_target"),
        Index("ix_personal_auto_outbound_calls_session_stage", "session_id", "stage"),
        Index("ix_personal_auto_outbound_calls_call_id", "tenant_id", "telephony_call_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("personal_auto_outbound_sessions.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("outbound_tasks.id", ondelete="RESTRICT"), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, ForeignKey("outbound_task_targets.id", ondelete="RESTRICT"), nullable=False)
    call_record_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("call_records.id", ondelete="SET NULL"), nullable=True)
    telephony_call_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    prescreen_result: Mapped[str | None] = mapped_column(String(40), nullable=True)
    intent_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    similarity: Mapped[float | None] = mapped_column(nullable=True)
    degraded_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assigned_agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    assignment_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hangup_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_utterance: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
