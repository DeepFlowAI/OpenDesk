"""
Satisfaction survey invitation records and submitted results.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class SatisfactionSurveyRecord(Base, TimestampMixin):
    __tablename__ = "satisfaction_survey_records"
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_satisfaction_records_conversation"),
        Index("ix_satisfaction_records_tenant_conversation", "tenant_id", "conversation_id"),
        Index("ix_satisfaction_records_tenant_status", "tenant_id", "status"),
        Index("ix_satisfaction_records_tenant_version", "tenant_id", "config_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    visitor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    invitation_source: Mapped[str] = mapped_column(String(24), nullable=False, default="agent", server_default="agent")
    invited_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invited_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="invited", server_default="invited")
    survey_types: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    service_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    product_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
