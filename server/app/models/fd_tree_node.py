"""
FdTreeNode model — tree nodes for single_select_tree / multi_select_tree fields
"""
from sqlalchemy import Boolean, Integer, String, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class FdTreeNode(Base, TimestampMixin):
    __tablename__ = "fd_tree_nodes"
    __table_args__ = (
        UniqueConstraint("field_definition_id", "value", name="uq_fd_tree_nodes_field_value"),
        Index("ix_fd_tree_nodes_field_id", "field_definition_id"),
        Index("ix_fd_tree_nodes_parent_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_definition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fd_field_definitions.id", ondelete="CASCADE"), nullable=False,
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("fd_tree_nodes.id", ondelete="SET NULL"), nullable=True,
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    field_definition: Mapped["FdFieldDefinition"] = relationship(
        "FdFieldDefinition", back_populates="tree_nodes",
    )
    children: Mapped[list["FdTreeNode"]] = relationship(
        "FdTreeNode", back_populates="parent",
        cascade="all, delete-orphan", lazy="selectin",
    )
    parent: Mapped["FdTreeNode | None"] = relationship(
        "FdTreeNode", back_populates="children", remote_side=[id],
    )


from app.models.fd_field_definition import FdFieldDefinition  # noqa: E402, F811
