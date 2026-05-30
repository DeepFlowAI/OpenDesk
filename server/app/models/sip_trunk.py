"""
SIP Trunk model — platform-level trunk catalog (not tenant-scoped).
"""
from typing import TYPE_CHECKING

from sqlalchemy import String, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.phone_number import PhoneNumber


class SipTrunk(Base, TimestampMixin):
    __tablename__ = "sip_trunks"
    __table_args__ = (
        Index(
            "uq_sip_trunks_trunk_name_lower",
            text("lower(trunk_name)"),
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    supplier_name: Mapped[str] = mapped_column(String(128), nullable=False)
    trunk_name: Mapped[str] = mapped_column(String(128), nullable=False)
    trunk_types: Mapped[list] = mapped_column(JSONB, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="enabled")
    peer_endpoints: Mapped[list] = mapped_column(JSONB, nullable=False)
    # Optional per-trunk outbound gateway config used when "outbound" is in
    # trunk_types. Shape: { server, port, user, pass, realm, callee_prefix }.
    # NULL → trunk is inbound-only (call.originate against it errors).
    outbound_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    phone_numbers: Mapped[list["PhoneNumber"]] = relationship(
        "PhoneNumber",
        back_populates="trunk",
    )
