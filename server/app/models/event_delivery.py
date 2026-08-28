"""Durable webhook delivery snapshot and retry state."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin

EVENT_DELIVERY_PENDING = "pending"
EVENT_DELIVERY_PROCESSING = "processing"
EVENT_DELIVERY_SUCCEEDED = "succeeded"
EVENT_DELIVERY_FAILED = "failed"


class EventDelivery(Base, TimestampMixin):
    """One immutable event snapshot targeted at one subscription."""

    __tablename__ = "event_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subscription_public_id",
            "event_id",
            name="uq_event_deliveries_tenant_subscription_event",
        ),
        Index("ix_event_deliveries_status_next", "status", "next_attempt_at"),
        Index(
            "ix_event_deliveries_tenant_subscription_created",
            "tenant_id",
            "subscription_public_id",
            "created_at",
        ),
        Index(
            "ix_event_deliveries_completed_retention",
            "completed_at",
            "id",
            postgresql_where=text(
                "status IN ('succeeded', 'failed') AND completed_at IS NOT NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True, default=uuid4
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("event_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    subscription_public_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    endpoint_url_snapshot: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret_ciphertext_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    source_module: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    api_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    is_test: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EVENT_DELIVERY_PENDING, server_default=EVENT_DELIVERY_PENDING
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
