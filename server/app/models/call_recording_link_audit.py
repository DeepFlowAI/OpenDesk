"""Audit trail for recording download links issued through the Open API."""
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class CallRecordingLinkAudit(Base, TimestampMixin):
    """One row per issued link; the link itself is never stored."""

    __tablename__ = "call_recording_link_audits"
    __table_args__ = (
        Index("ix_call_recording_link_audit_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # No foreign key: the audit outlives a deleted API key.
    api_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_key_name: Mapped[str] = mapped_column(String(100), nullable=False)
    call_public_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    recording_public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
