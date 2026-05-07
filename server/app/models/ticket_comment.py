"""
TicketComment model — comment thread on a ticket detail page.

Stores rich-text body + optional attachments authored by an employee.
Listed in the right-side activity panel under the `Comments` and `All` tabs.
"""
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class TicketComment(Base, TimestampMixin):
    __tablename__ = "ticket_comments"
    __table_args__ = (
        Index(
            "ix_ticket_comments_tenant_ticket_created",
            "tenant_id",
            "ticket_id",
            "created_at",
        ),
        Index("ix_ticket_comments_ticket", "ticket_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    # Author resolves to an employee. SET NULL on employee deletion so history
    # remains readable; `author_name` is kept as a fallback display value.
    author_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Rich-text body. Either `body` or `attachments` must be non-empty;
    # validated in the service layer (DB stays permissive for future channels).
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_format: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="html"
    )

    # Attachment list: [{url, name, size, content_type}]
    # Mirrors the JSON shape returned by /v1/upload/custom-field-file.
    attachments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
