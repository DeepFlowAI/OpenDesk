"""
SipExtension — a tenant-scoped SIP account (extension) that can be uniquely
bound to one agent. Holds registration credentials (hashed + masked) and the
current registration status reported by the media kernel.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import AuditActorMixin, TimestampMixin


class SipExtension(Base, TimestampMixin, AuditActorMixin):
    __tablename__ = "sip_extensions"
    __table_args__ = (
        # Extension number is unique within a tenant.
        UniqueConstraint(
            "tenant_id", "extension_number", name="uq_sip_ext_tenant_number"
        ),
        # SIP user id is unique across the registration domain.
        UniqueConstraint("sip_user_id", name="uq_sip_ext_sip_user_id"),
        # One agent may be bound to at most one extension. Multiple NULLs are
        # allowed by SQL semantics, so unbound extensions do not conflict.
        UniqueConstraint(
            "bound_employee_id", name="uq_sip_ext_bound_employee"
        ),
        Index("ix_sip_ext_tenant_id", "tenant_id"),
        Index("ix_sip_ext_tenant_active", "tenant_id", "is_active"),
        Index("ix_sip_ext_tenant_reg_status", "tenant_id", "registration_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    extension_number: Mapped[str] = mapped_column(String(10), nullable=False)

    # System-generated identity used for SIP registration/addressing.
    sip_user_id: Mapped[str] = mapped_column(String(80), nullable=False)
    # System-generated Digest auth account. Same value as sip_user_id today,
    # kept as its own column so addressing and auth identity can diverge later
    # without a schema change.
    auth_account: Mapped[str] = mapped_column(String(80), nullable=False)

    auth_password_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_password_masked: Mapped[str] = mapped_column(String(40), nullable=False)

    registration_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unregistered", server_default="unregistered"
    )
    last_registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    bound_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
