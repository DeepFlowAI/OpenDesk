"""
FdFormLayout model — ticket form layout definition
"""
from sqlalchemy import Integer, String, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class FdFormLayout(Base, TimestampMixin):
    __tablename__ = "fd_form_layouts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scene", name="uq_fd_form_layouts_tenant_scene"),
        Index("ix_fd_form_layouts_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scene: Mapped[str] = mapped_column(String(32), nullable=False)
    columns_per_row: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    label_position: Mapped[str] = mapped_column(String(16), nullable=False, server_default="top")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    tabs: Mapped[list["FdFormLayoutTab"]] = relationship(
        "FdFormLayoutTab", back_populates="layout",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="FdFormLayoutTab.sort_order",
    )
    interaction_rules: Mapped[list["FdInteractionRule"]] = relationship(
        "FdInteractionRule", back_populates="layout",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="FdInteractionRule.sort_order",
    )


from app.models.fd_form_layout_tab import FdFormLayoutTab  # noqa: E402
from app.models.fd_interaction_rule import FdInteractionRule  # noqa: E402
