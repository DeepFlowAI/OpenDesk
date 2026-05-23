"""
WelcomeMessageRule — visitor chat welcome message rules.
"""
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class WelcomeMessageRule(Base, TimestampMixin):
    __tablename__ = "welcome_message_rules"
    __table_args__ = (
        Index("ix_welcome_message_rules_tenant_id", "tenant_id"),
        Index("ix_welcome_message_rules_tenant_priority", "tenant_id", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    content: Mapped[str] = mapped_column(Text, nullable=False)
