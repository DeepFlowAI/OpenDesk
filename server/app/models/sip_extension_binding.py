"""
SipExtensionBinding — which agents are eligible to use a shared SIP extension.

Binding grants qualification only; the exclusive occupant is tracked on
``SipExtension.current_occupant_employee_id``.
"""
from sqlalchemy import ForeignKey, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class SipExtensionBinding(Base, TimestampMixin):
    __tablename__ = "sip_extension_bindings"
    __table_args__ = (
        # One agent may be bound to at most one extension.
        UniqueConstraint("employee_id", name="uq_sip_ext_binding_employee"),
        UniqueConstraint(
            "extension_id", "employee_id", name="uq_sip_ext_binding_ext_employee"
        ),
        Index("ix_sip_ext_binding_extension_id", "extension_id"),
        Index("ix_sip_ext_binding_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    extension_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sip_extensions.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
