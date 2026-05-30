"""
Ticket model — work order / ticket entity with dynamic slot columns
"""
from sqlalchemy import Integer, String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import AuditActorMixin, MetadataMixin, SlotColumnMixin


class Ticket(Base, MetadataMixin, AuditActorMixin, SlotColumnMixin):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_tenant", "tenant_id"),
        Index("ix_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_tickets_user", "user_id"),
        Index("ix_tickets_agent", "agent_id"),
        Index("ix_tickets_assignee_group", "assignee_group_id"),
        Index("ix_tickets_conversation", "conversation_id"),
        Index("ix_tickets_call_record", "call_record_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    ticket_number: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    layout_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fd_form_layouts.id", ondelete="SET NULL"), nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    call_record_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("call_records.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    assignee_group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="open")
    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
