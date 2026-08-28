"""Call satisfaction execution and immutable answer snapshots."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class CallSatisfactionExecution(Base, TimestampMixin):
    """One version-locked satisfaction survey for a customer call."""

    __tablename__ = "call_satisfaction_executions"
    __table_args__ = (
        UniqueConstraint("call_record_id", name="uq_cse_call_record"),
        Index("ix_cse_tenant_status_started", "tenant_id", "status", "started_at"),
        Index(
            "ix_cse_tenant_flow_version",
            "tenant_id",
            "satisfaction_flow_version_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False
    )
    satisfaction_flow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("satisfaction_flows.id", ondelete="RESTRICT"), nullable=False
    )
    satisfaction_flow_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("satisfaction_flow_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trigger_source: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="preparing", server_default="preparing"
    )
    flow_name_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    flow_version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    queue_type_snapshot: Mapped[str | None] = mapped_column(String(24), nullable=True)
    queue_id_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answer_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    answers: Mapped[list["CallSatisfactionAnswer"]] = relationship(
        "CallSatisfactionAnswer",
        back_populates="execution",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class CallSatisfactionAnswer(Base):
    """A mapped option snapshot; raw DTMF is deliberately not stored."""

    __tablename__ = "call_satisfaction_answers"
    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "question_node_id",
            name="uq_csa_execution_question",
        ),
        Index(
            "ix_csa_tenant_execution_order",
            "tenant_id",
            "execution_id",
            "question_order",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("call_satisfaction_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question_name_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    question_order: Mapped[int] = mapped_column(Integer, nullable=False)
    option_id: Mapped[str] = mapped_column(String(64), nullable=False)
    option_label_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    execution: Mapped[CallSatisfactionExecution] = relationship(
        CallSatisfactionExecution,
        back_populates="answers",
    )
