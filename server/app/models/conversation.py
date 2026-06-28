"""
Conversation model — a chat session between an end user and an agent
"""
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin
from app.enums import ConversationStatus


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_conversations_public_id"),
        UniqueConstraint("share_code", name="uq_conversations_share_code"),
        Index("ix_conversations_tenant_agent_status", "tenant_id", "agent_id", "status"),
        Index("ix_conversations_tenant_status", "tenant_id", "status"),
        Index("ix_conversations_tenant_visitor", "tenant_id", "visitor_id"),
        Index("ix_conversations_last_message_at", "last_message_at"),
        Index("ix_conversations_tenant_started_at", "tenant_id", "started_at"),
        Index("ix_conversations_channel_id", "channel_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    share_code: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    visitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ConversationStatus.QUEUED.value, server_default="queued"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(200), nullable=True)
    visitor_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visitor_browser: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visitor_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Materialized queue summary (maintained by the queue engine on assignment/terminal).
    last_assigned_queue_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_assigned_queue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_assigned_queue_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_queue_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Materialized queue lifecycle (redundant, read-only): entered/assigned
    # timestamps and the final result over the conversation's substantial queue
    # tasks, so session records read them without re-aggregating queue_tasks.
    queue_entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queue_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queue_result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Materialized basic report fields (redundant, read-only copies of the
    # OpenAgent identity/handoff fields and the session timestamps).
    had_bot_session: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    bot_handoff_succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    bot_handoff_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Materialized message counts (redundant, read-only): visitor/agent feed the
    # report message totals; bot/human phase split visitor+bot vs visitor+agent
    # around the human-takeover anchor (started_at on bot conversations).
    visitor_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    agent_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bot_phase_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bot_phase_visitor_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    human_phase_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    human_phase_visitor_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    human_phase_agent_message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    first_human_response_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Materialized human-agent response stats over the whole conversation: the
    # number of visitor-block -> agent-reply transitions and the average
    # whole-second response time across them. Both NULL while in progress.
    agent_response_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_avg_response_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_agent_agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_agent_agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    open_agent_conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_agent_conversation_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    open_agent_last_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    open_agent_last_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    open_agent_handoff_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    open_agent_handoff_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # Materialized reception-segment aggregates (redundant, read-only). Written
    # in bulk after the conversation ends so session-record lists read them
    # without aggregating the per-segment fact table at query time.
    reception_segment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reception_transfer_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reception_final_agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reception_participants: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    reception_generation_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    visitor: Mapped["User"] = relationship("User", lazy="selectin")
    agent: Mapped["Employee | None"] = relationship("Employee", lazy="selectin")
    channel: Mapped["Channel | None"] = relationship("Channel", lazy="selectin")
    group: Mapped["EmployeeGroup | None"] = relationship("EmployeeGroup", lazy="selectin")
