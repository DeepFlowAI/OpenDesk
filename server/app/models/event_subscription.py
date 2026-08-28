"""Tenant event subscription configuration and management audit models."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class EventSubscription(Base, TimestampMixin):
    """A reusable tenant-scoped HTTPS webhook destination."""

    __tablename__ = "event_subscriptions"
    __table_args__ = (
        Index("ix_event_subscriptions_tenant_updated", "tenant_id", "updated_at"),
        Index("ix_event_subscriptions_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    secret_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    previous_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_secret_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    secret_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def masked_secret(self) -> str:
        """Return a display-safe representation of the webhook secret."""
        return f"odwhsec_••••••••••{self.secret_last_four}"


class EventSubscriptionAudit(Base, TimestampMixin):
    """A non-sensitive management action record retained after subscription deletion."""

    __tablename__ = "event_subscription_audits"
    __table_args__ = (
        Index(
            "ix_event_subscription_audits_tenant_subscription_created",
            "tenant_id",
            "subscription_public_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subscription_public_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
