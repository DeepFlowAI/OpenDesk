"""
CsSummaryConfig model — conversation minutes configuration (one per tenant)
"""
from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class CsSummaryConfig(Base, TimestampMixin):
    __tablename__ = "cs_summary_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_cs_summary_configs_tenant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    fields: Mapped[list["CsSummaryConfigField"]] = relationship(
        "CsSummaryConfigField", back_populates="config", cascade="all, delete-orphan",
        order_by="CsSummaryConfigField.sort_order",
    )
    interaction_rules: Mapped[list["CsSummaryInteractionRule"]] = relationship(
        "CsSummaryInteractionRule", back_populates="config", cascade="all, delete-orphan",
        order_by="CsSummaryInteractionRule.sort_order",
    )


from app.models.cs_summary_config_field import CsSummaryConfigField  # noqa: E402
from app.models.cs_summary_interaction_rule import CsSummaryInteractionRule  # noqa: E402
