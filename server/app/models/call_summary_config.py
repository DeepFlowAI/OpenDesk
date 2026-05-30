"""
CallSummaryConfig model - call summary configuration (one per tenant)
"""
from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class CallSummaryConfig(Base, TimestampMixin):
    __tablename__ = "call_summary_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_call_summary_configs_tenant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    fields: Mapped[list["CallSummaryConfigField"]] = relationship(
        "CallSummaryConfigField", back_populates="config", cascade="all, delete-orphan",
        order_by="CallSummaryConfigField.sort_order",
    )
    interaction_rules: Mapped[list["CallSummaryInteractionRule"]] = relationship(
        "CallSummaryInteractionRule", back_populates="config", cascade="all, delete-orphan",
        order_by="CallSummaryInteractionRule.sort_order",
    )


from app.models.call_summary_config_field import CallSummaryConfigField  # noqa: E402
from app.models.call_summary_interaction_rule import CallSummaryInteractionRule  # noqa: E402
