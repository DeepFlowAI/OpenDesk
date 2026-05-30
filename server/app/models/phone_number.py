"""
Phone number model — platform-level DID catalog with optional tenant assignment.
"""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.sip_trunk import SipTrunk
    from app.models.tenant import Tenant


class PhoneNumber(Base, TimestampMixin):
    __tablename__ = "phone_numbers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    call_types: Mapped[list] = mapped_column(JSONB, nullable=False)
    trunk_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("sip_trunks.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("tenants.tenant_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="available")
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    called_number_prefix: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outbound_time_slots: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    trunk: Mapped["SipTrunk | None"] = relationship("SipTrunk", back_populates="phone_numbers")
    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant",
        primaryjoin="PhoneNumber.tenant_id == Tenant.tenant_id",
        foreign_keys="PhoneNumber.tenant_id",
        viewonly=True,
    )
