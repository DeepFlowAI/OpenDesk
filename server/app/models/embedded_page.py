"""
EmbeddedPage — admin-configured third-party pages embedded into agent workspaces.

Each row is one embedded page (iframe URL or controlled React code) bound to a
fixed location (chat auxiliary area, call screen-pop area). The workspace
injects the current business context at runtime; nothing conversation-specific
is persisted here.
"""
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class EmbeddedPage(Base, TimestampMixin):
    __tablename__ = "embedded_pages"
    __table_args__ = (
        Index("ix_embedded_pages_tenant_location", "tenant_id", "location"),
        Index("ix_embedded_pages_tenant_location_enabled", "tenant_id", "location", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    location: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    page_type: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    react_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    default_focus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
