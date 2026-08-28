"""Auto outbound task event subscription binding and audit models."""
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class AutoOutboundEventSubscription(Base, TimestampMixin):
    """The single global webhook subscription selected by one auto outbound task."""

    __tablename__ = "auto_outbound_event_subscriptions"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_auto_outbound_event_subscriptions_task"),
        Index("ix_auto_outbound_event_subscriptions_tenant_task", "tenant_id", "task_id"),
        Index(
            "ix_auto_outbound_event_subscriptions_tenant_subscription",
            "tenant_id",
            "subscription_public_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("auto_outbound_tasks.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event_subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_public_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    created_by_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )


class AutoOutboundEventSubscriptionAudit(Base, TimestampMixin):
    """Non-sensitive audit trail for task subscription configuration changes."""

    __tablename__ = "auto_outbound_event_subscription_audits"
    __table_args__ = (
        Index(
            "ix_auto_outbound_event_subscription_audits_tenant_task_created",
            "tenant_id",
            "task_public_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("auto_outbound_tasks.id", ondelete="SET NULL"), nullable=True
    )
    task_public_id: Mapped[int] = mapped_column(Integer, nullable=False)
    subscription_public_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
