"""
CallSummaryConfigField model - fields selected for call summary config
"""
from sqlalchemy import Boolean, Integer, String, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class CallSummaryConfigField(Base, TimestampMixin):
    __tablename__ = "call_summary_config_fields"
    __table_args__ = (
        UniqueConstraint("config_id", "field_definition_id", name="uq_call_summary_cfg_field_def"),
        UniqueConstraint("config_id", "field_key", name="uq_call_summary_cfg_field_key"),
        Index("ix_call_summary_config_fields_config", "config_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("call_summary_configs.id", ondelete="CASCADE"), nullable=False,
    )
    field_definition_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("fd_field_definitions.id", ondelete="CASCADE"), nullable=True,
    )
    field_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    config: Mapped["CallSummaryConfig"] = relationship("CallSummaryConfig", back_populates="fields")
    field_definition: Mapped["FdFieldDefinition | None"] = relationship("FdFieldDefinition", lazy="selectin")


from app.models.call_summary_config import CallSummaryConfig  # noqa: E402
from app.models.fd_field_definition import FdFieldDefinition  # noqa: E402
