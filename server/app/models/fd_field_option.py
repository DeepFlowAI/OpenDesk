"""
FdFieldOption model — options for single_select / multi_select fields
"""
from sqlalchemy import Boolean, Integer, String, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class FdFieldOption(Base, TimestampMixin):
    __tablename__ = "fd_field_options"
    __table_args__ = (
        UniqueConstraint("field_definition_id", "value", name="uq_fd_field_options_field_value"),
        Index("ix_fd_field_options_field_id", "field_definition_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_definition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fd_field_definitions.id", ondelete="CASCADE"), nullable=False,
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    field_definition: Mapped["FdFieldDefinition"] = relationship(
        "FdFieldDefinition", back_populates="options",
    )


from app.models.fd_field_definition import FdFieldDefinition  # noqa: E402, F811
