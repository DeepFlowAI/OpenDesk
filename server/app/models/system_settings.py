"""
SystemSettings model — per-tenant system configuration
"""
from sqlalchemy import Boolean, String, Integer, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.constants.lingomaster import DEFAULT_AGENT_TRANSLATION_PROMPT, DEFAULT_VISITOR_TRANSLATION_PROMPT
from app.models.base import TimestampMixin


class SystemSettings(Base, TimestampMixin):
    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_system_settings_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    default_language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="zh")
    default_timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Shanghai")
    organization_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    bridge_asr_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    call_wrapup_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30", default=30
    )
    lingomaster_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    lingomaster_visitor_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=DEFAULT_VISITOR_TRANSLATION_PROMPT,
        default=DEFAULT_VISITOR_TRANSLATION_PROMPT,
    )
    lingomaster_agent_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=DEFAULT_AGENT_TRANSLATION_PROMPT,
        default=DEFAULT_AGENT_TRANSLATION_PROMPT,
    )
