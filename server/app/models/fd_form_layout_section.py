"""
FdFormLayoutSection model — sections within a tab
"""
from sqlalchemy import Boolean, Integer, String, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class FdFormLayoutSection(Base, TimestampMixin):
    __tablename__ = "fd_form_layout_sections"
    __table_args__ = (
        Index("ix_fd_form_layout_sections_tab", "tab_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tab_id: Mapped[int] = mapped_column(Integer, ForeignKey("fd_form_layout_tabs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_collapsed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    tab: Mapped["FdFormLayoutTab"] = relationship("FdFormLayoutTab", back_populates="sections")
    fields: Mapped[list["FdFormLayoutField"]] = relationship(
        "FdFormLayoutField", back_populates="section",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="FdFormLayoutField.sort_order",
    )


from app.models.fd_form_layout_tab import FdFormLayoutTab  # noqa: E402
from app.models.fd_form_layout_field import FdFormLayoutField  # noqa: E402
