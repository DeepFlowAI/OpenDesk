"""Successful Web SDK form-message submissions and immutable field snapshots."""

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ChannelFormSubmission(Base, TimestampMixin):
    __tablename__ = "channel_form_submissions"
    __table_args__ = (
        UniqueConstraint("ticket_id", name="uq_channel_form_submissions_ticket"),
        UniqueConstraint(
            "tenant_id",
            "channel_id",
            "visitor_external_id",
            "idempotency_key",
            name="uq_channel_form_submissions_idempotency",
        ),
        Index("ix_channel_form_submissions_tenant_ticket", "tenant_id", "ticket_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channel_form_config_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ticket_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    visitor_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    visitor_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="outside_service_hours",
    )
    queue_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    queue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    field_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
