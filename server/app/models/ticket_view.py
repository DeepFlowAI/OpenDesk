"""
TicketView model — saved view configurations for ticket lists
"""
from sqlalchemy import Boolean, Integer, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class TicketView(Base, TimestampMixin):
    __tablename__ = "ticket_views"
    __table_args__ = (
        Index("ix_ticket_views_tenant", "tenant_id"),
        Index("ix_ticket_views_tenant_sort", "tenant_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    condition_logic: Mapped[str] = mapped_column(String(8), nullable=False, server_default="and")
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    group_field_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("fd_field_definitions.id", ondelete="SET NULL"), nullable=True
    )
    custom_columns_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    columns_config: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
