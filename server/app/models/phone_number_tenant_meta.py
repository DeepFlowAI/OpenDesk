"""
Per-tenant metadata for platform phone numbers (tags).
"""
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class PhoneNumberTenantMeta(Base, TimestampMixin):
    __tablename__ = "phone_number_tenant_meta"
    __table_args__ = (
        UniqueConstraint("tenant_id", "phone_number_id", name="uq_phone_number_tenant_meta"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phone_number_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("phone_numbers.id", ondelete="CASCADE"),
        nullable=False,
    )
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
