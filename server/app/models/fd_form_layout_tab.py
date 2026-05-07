"""
FdFormLayoutTab model — tabs within a form layout (outermost container)
"""
from sqlalchemy import Integer, String, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class FdFormLayoutTab(Base, TimestampMixin):
    __tablename__ = "fd_form_layout_tabs"
    __table_args__ = (
        Index("ix_fd_form_layout_tabs_layout", "layout_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    layout_id: Mapped[int] = mapped_column(Integer, ForeignKey("fd_form_layouts.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    layout: Mapped["FdFormLayout"] = relationship("FdFormLayout", back_populates="tabs")
    sections: Mapped[list["FdFormLayoutSection"]] = relationship(
        "FdFormLayoutSection", back_populates="tab",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="FdFormLayoutSection.sort_order",
    )


from app.models.fd_form_layout import FdFormLayout  # noqa: E402
from app.models.fd_form_layout_section import FdFormLayoutSection  # noqa: E402
