"""Persistent platform-wide LLM work queue."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class PlatformLLMCall(Base, TimestampMixin):
    __tablename__ = "platform_llm_calls"
    __table_args__ = (
        Index("uq_platform_llm_calls_idempotency", "idempotency_key", unique=True),
        Index("ix_platform_llm_calls_dispatch", "status", "available_at", "created_at"),
        Index("ix_platform_llm_calls_business", "business_type", "business_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    business_type: Mapped[str] = mapped_column(String(48), nullable=False)
    business_id: Mapped[str] = mapped_column(String(96), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(192), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    execution_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
