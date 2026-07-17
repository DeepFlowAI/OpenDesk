"""
AgentCallDevice — the agent's persisted "current call device" selection.

One row per employee. ``device_type`` is a string enum (``webrtc`` |
``sip_phone``) rather than a boolean so future device types (e.g. mobile)
can be added without a schema change. Persisting the selection lets the
workspace restore the agent's last device on next login.
"""
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class AgentCallDevice(Base, TimestampMixin):
    __tablename__ = "agent_call_devices"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "employee_id", name="uq_agent_call_device_tenant_employee"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    # Current device type. Extensible string enum: webrtc | sip_phone | ...
    device_type: Mapped[str] = mapped_column(String(24), nullable=False)
