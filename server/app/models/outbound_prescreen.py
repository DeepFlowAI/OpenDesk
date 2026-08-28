"""Outbound prescreen intent configuration models."""
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.configs.settings import settings
from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.vector import Vector


class OutboundPrescreenIntent(Base, TimestampMixin):
    __tablename__ = "outbound_prescreen_intents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "intent_key", name="uq_outbound_prescreen_intents_tenant_key"),
        UniqueConstraint("tenant_id", "name", name="uq_outbound_prescreen_intents_tenant_name"),
        Index("ix_outbound_prescreen_intents_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    intent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    similarity_threshold: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("0.860"), server_default="0.860"
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class OutboundPrescreenIntentExample(Base, TimestampMixin):
    __tablename__ = "outbound_prescreen_intent_examples"
    __table_args__ = (
        UniqueConstraint(
            "intent_id",
            "example_type",
            "normalized_text",
            name="uq_outbound_prescreen_examples_intent_type_text",
        ),
        Index(
            "ix_outbound_prescreen_examples_tenant_intent_type",
            "tenant_id",
            "intent_id",
            "example_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    intent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("outbound_prescreen_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    example_type: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.KNOWLEDGE_EMBEDDING_DIMENSION), nullable=True
    )
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ready", server_default="ready"
    )
