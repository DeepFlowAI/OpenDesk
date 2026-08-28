"""Target CDR model for one customer-facing root call."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class CallRecord(Base, TimestampMixin):
    """Query-oriented projection of the immutable call-event trajectory."""

    __tablename__ = "call_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "call_id", name="uq_cr_tenant_call_id"),
        UniqueConstraint("public_id", name="uq_cr_public_id"),
        UniqueConstraint("ended_event_id", name="uq_cr_ended_event_id"),
        CheckConstraint(
            "(last_queue_type IS NULL) = (last_queue_id IS NULL)",
            name="ck_cr_last_queue_pair",
        ),
        Index("ix_cr_tenant_started", "tenant_id", "started_at", "id"),
        Index("ix_cr_tenant_lifecycle_started", "tenant_id", "lifecycle_status", "started_at"),
        Index("ix_cr_tenant_result_started", "tenant_id", "call_result", "started_at"),
        Index("ix_cr_tenant_hangup_party_started", "tenant_id", "hangup_party", "started_at"),
        Index("ix_cr_tenant_user_started", "tenant_id", "user_id", "started_at"),
        Index(
            "ix_cr_tenant_last_agent_started",
            "tenant_id",
            "last_serving_agent_id",
            "started_at",
        ),
        Index(
            "ix_cr_tenant_last_queue_started",
            "tenant_id",
            "last_queue_type",
            "last_queue_id",
            "started_at",
        ),
        Index("ix_cr_tenant_customer_number", "tenant_id", "customer_number"),
        Index("ix_cr_tenant_service_number", "tenant_id", "service_number"),
        Index(
            "ix_cr_tenant_satisfaction_result_started",
            "tenant_id",
            "satisfaction_result",
            "started_at",
        ),
        Index(
            "ix_cr_tenant_satisfaction_source_started",
            "tenant_id",
            "satisfaction_trigger_source",
            "started_at",
        ),
        Index("ix_cr_conversation", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, default=uuid4
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    root_call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    call_source: Mapped[str] = mapped_column(String(24), nullable=False)
    custom_business_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    customer_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    service_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    voice_flow_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("voice_flows.id", ondelete="SET NULL"), nullable=True
    )
    voice_flow_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("voice_flow_versions.id", ondelete="SET NULL"), nullable=True
    )
    initiator_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    last_serving_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    last_queue_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    last_queue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    lifecycle_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    customer_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_agent_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_service_ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    finalization_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ended_event_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    result_rule_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_reception_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    call_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hangup_party: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hangup_reason_code: Mapped[str | None] = mapped_column(String(48), nullable=True)

    total_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    customer_ring_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    agent_wait_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    customer_agent_talk_duration_ms: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    satisfaction_result: Mapped[str | None] = mapped_column(String(24), nullable=True)
    satisfaction_trigger_source: Mapped[str | None] = mapped_column(
        String(24), nullable=True
    )
    satisfaction_primary_option_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    satisfaction_primary_option_label: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    satisfaction_answer_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    satisfaction_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    satisfaction_projected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recording_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
