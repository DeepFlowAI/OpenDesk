"""
FdInteractionRule model — interaction rules for form layouts
"""
from sqlalchemy import Boolean, Integer, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class FdInteractionRule(Base, TimestampMixin):
    __tablename__ = "fd_interaction_rules"
    __table_args__ = (
        Index("ix_fd_interaction_rules_layout", "layout_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    layout_id: Mapped[int] = mapped_column(Integer, ForeignKey("fd_form_layouts.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    condition_logic: Mapped[str] = mapped_column(String(8), nullable=False, server_default="and")
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    layout: Mapped["FdFormLayout"] = relationship("FdFormLayout", back_populates="interaction_rules")


from app.models.fd_form_layout import FdFormLayout  # noqa: E402
