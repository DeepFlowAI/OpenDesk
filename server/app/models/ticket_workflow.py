"""
TicketWorkflow — workflow header for ticket automation.

Versioned graph snapshots live in ticket_workflow_versions; current_version_id
points at the active snapshot used by execution.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class TicketWorkflow(Base, TimestampMixin):
    __tablename__ = "ticket_workflows"
    __table_args__ = (
        Index("ix_ticket_workflows_tenant_sort", "tenant_id", "sort_order", "id"),
        Index("ix_ticket_workflows_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    current_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ticket_workflow_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    versions: Mapped[list["TicketWorkflowVersion"]] = relationship(  # noqa: F821
        "TicketWorkflowVersion",
        back_populates="workflow",
        primaryjoin="TicketWorkflow.id == TicketWorkflowVersion.workflow_id",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    current_version: Mapped["TicketWorkflowVersion | None"] = relationship(  # noqa: F821
        "TicketWorkflowVersion",
        primaryjoin="TicketWorkflow.current_version_id == TicketWorkflowVersion.id",
        foreign_keys=[current_version_id],
        post_update=True,
        lazy="joined",
    )
