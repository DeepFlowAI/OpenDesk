"""
TicketChange model — field-level audit trail for ticket updates.
"""
from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class TicketChange(Base, TimestampMixin):
    __tablename__ = "ticket_changes"
    __table_args__ = (
        Index("ix_ticket_changes_tenant_ticket_created", "tenant_id", "ticket_id", "created_at"),
        Index("ix_ticket_changes_ticket", "ticket_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="user")
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    field_label: Mapped[str] = mapped_column(String(128), nullable=False)
    field_source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ticket")
    old_value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
