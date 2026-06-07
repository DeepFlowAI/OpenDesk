"""
TicketWorkflowVersion — immutable graph snapshot for ticket automation.
"""
from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import AuditActorMixin, TimestampMixin


class TicketWorkflowVersion(Base, TimestampMixin, AuditActorMixin):
    __tablename__ = "ticket_workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version_no", name="uq_twv_workflow_version"),
        Index("ix_twv_tenant_workflow", "tenant_id", "workflow_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ticket_workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(200), nullable=True)

    workflow: Mapped["TicketWorkflow"] = relationship(  # noqa: F821
        "TicketWorkflow",
        back_populates="versions",
        foreign_keys=[workflow_id],
    )
