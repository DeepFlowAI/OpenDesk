"""
CallTranscriptSegment — one finalized line of a bridged call's live transcript.

Appended as ASR final results arrive during a human↔human bridge (see the
orchestrator's transcript relay). Immutable; conversation order is the row id.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CallTranscriptSegment(Base):
    __tablename__ = "call_transcript_segments"
    __table_args__ = (
        Index("ix_cts_tenant_call", "tenant_id", "call_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    # 'user' (caller) or 'agent' (the bridged seat).
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # ASR sequence within one leg's stream; not globally ordered, kept for reference.
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
