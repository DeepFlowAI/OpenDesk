"""
CallSummaryInteractionRule model - interaction rules for call summary forms
"""
from sqlalchemy import Boolean, Integer, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class CallSummaryInteractionRule(Base, TimestampMixin):
    __tablename__ = "call_summary_interaction_rules"
    __table_args__ = (
        Index("ix_call_summary_interaction_rules_config", "config_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("call_summary_configs.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    condition_logic: Mapped[str] = mapped_column(String(8), nullable=False, server_default="and")
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    config: Mapped["CallSummaryConfig"] = relationship("CallSummaryConfig", back_populates="interaction_rules")


from app.models.call_summary_config import CallSummaryConfig  # noqa: E402
