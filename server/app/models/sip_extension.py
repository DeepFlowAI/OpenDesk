"""
SipExtension — a tenant-scoped SIP account (extension).

Multiple agents may be bound via ``sip_extension_bindings``; at most one
``current_occupant_employee_id`` holds exclusive use of the shared phone.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import AuditActorMixin, TimestampMixin


class SipExtension(Base, TimestampMixin, AuditActorMixin):
    __tablename__ = "sip_extensions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "extension_number", name="uq_sip_ext_tenant_number"
        ),
        UniqueConstraint("sip_user_id", name="uq_sip_ext_sip_user_id"),
        Index("ix_sip_ext_tenant_id", "tenant_id"),
        Index("ix_sip_ext_tenant_active", "tenant_id", "is_active"),
        Index("ix_sip_ext_tenant_reg_status", "tenant_id", "registration_status"),
        Index("ix_sip_ext_current_occupant", "current_occupant_employee_id"),
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
    auth_password_ciphertext: Mapped[str | None] = mapped_column(String(255), nullable=True)

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

    # Agent currently holding exclusive occupancy of this shared extension.
    # Binding alone does not set this; switching to SIP phone acquires it.
    current_occupant_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
