"""One durable recording artifact belonging to a call record."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class CallRecording(Base, TimestampMixin):
    __tablename__ = "call_recordings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "recording_id", name="uq_call_recordings_tenant_recording"),
        Index("ix_call_recordings_record_started", "call_record_id", "started_at"),
        Index("uq_call_recordings_public_id", "public_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    recording_id: Mapped[str] = mapped_column(String(96), nullable=False)
    call_leg_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_event_id: Mapped[str] = mapped_column(String(96), nullable=False)
