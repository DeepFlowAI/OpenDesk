"""Materialized row-level access facts for call records."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CallRecordAccessScope(Base):
    __tablename__ = "call_record_access_scopes"
    __table_args__ = (
        UniqueConstraint(
            "call_record_id",
            "subject_type",
            "subject_id",
            "reason",
            name="uq_cras_record_subject_reason",
        ),
        UniqueConstraint(
            "tenant_id",
            "source_event_id",
            "subject_type",
            "subject_id",
            "reason",
            name="uq_cras_source_subject_reason",
        ),
        Index(
            "ix_cras_tenant_subject_record",
            "tenant_id",
            "subject_type",
            "subject_id",
            "call_record_id",
        ),
        Index("ix_cras_call_record", "call_record_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(96), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
