"""
Scheduling Center rule-based scheduling models.
"""
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ScheduleRuleSet(Base, TimestampMixin):
    """Scheduling rule set: coverage targets, work-hour constraints and
    rotation templates used by rule-based generation and validation.

    Configuration payloads are stored as JSONB (few rows per tenant):

    - ``default_group_ids``: ``[employee_group_id, ...]``
    - ``targets_enabled``: when false, generation ignores coverage targets
    - ``targets``: ``{"<shift_id>": {"min": [...7], "target": [...7], "max": [...7]}}``
      (legacy ``{"<shift_id>": [mon..sun]}`` is normalized on read)
    - ``constraints``: ``{"<constraint_key>": {"enabled": bool, "level": "hard"|"soft", "value"?: int}}``
    - ``rotation_templates``: ``[{"id", "name", "is_default", "days": [{"kind": "shift", "shift_id"} | {"kind": "off"}]}]``
    """

    __tablename__ = "schedule_rule_sets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_schedule_rule_sets_tenant_name"),
        Index("ix_schedule_rule_sets_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    default_group_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    targets_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    targets: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    constraints: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    rotation_templates: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
