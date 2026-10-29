"""Call event subscription rules and their configuration audits."""
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class CallEventSubscriptionRule(Base, TimestampMixin):
    """Routes matching call facts to exactly one global webhook subscription."""

    __tablename__ = "call_event_subscription_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_call_event_rule_tenant_name"),
        UniqueConstraint(
            "tenant_id", "subscription_id", name="uq_call_event_rule_tenant_subscription"
        ),
        Index("ix_call_event_rule_tenant_updated", "tenant_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        unique=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    subscription_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event_subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    event_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    directions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    call_sources: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_by_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )


class CallEventSubscriptionRuleAudit(Base, TimestampMixin):
    """Non-sensitive audit trail for call event subscription rule changes."""

    __tablename__ = "call_event_subscription_rule_audits"
    __table_args__ = (
        Index("ix_call_event_rule_audit_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    rule_public_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
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
