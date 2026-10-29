"""Durable, employee-owned export jobs."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ExportTask(Base, TimestampMixin):
    __tablename__ = "export_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", "idempotency_key", name="uq_export_task_submission"),
        Index("ix_export_task_owner", "tenant_id", "employee_id", "created_at", "id"),
        Index("ix_export_task_queue", "status", "created_at"),
        Index("uq_export_task_running_owner", "tenant_id", "employee_id", unique=True,
              postgresql_where=text("status = 'running'")),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    idempotency_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(64))
    name: Mapped[dict] = mapped_column(JSONB)
    business_type: Mapped[dict] = mapped_column(JSONB)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[dict] = mapped_column(JSONB)
    safe_summary: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int | None] = mapped_column(Integer)
    file_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    manifest: Mapped[dict | None] = mapped_column(JSONB)
    scope_reduced: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
