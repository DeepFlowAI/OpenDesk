"""
FdFormLayoutField model — field placement within a section

field_source values:
  - ticket        : ticket system field or ticket custom field (default)
  - ticket_metadata: metadata field (created_at, updated_at) — ticket_detail only
  - user          : user domain field (reference, readonly) — ticket_detail only
  - organization  : organization domain field (reference, readonly) — ticket_detail only
"""
from sqlalchemy import Integer, String, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class FdFormLayoutField(Base, TimestampMixin):
    __tablename__ = "fd_form_layout_fields"
    __table_args__ = (
        UniqueConstraint("section_id", "field_definition_id", "field_source", name="uq_fd_layout_fields_section_field_def_src"),
        UniqueConstraint("section_id", "field_key", "field_source", name="uq_fd_layout_fields_section_field_key_src"),
        Index("ix_fd_form_layout_fields_section", "section_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(Integer, ForeignKey("fd_form_layout_sections.id", ondelete="CASCADE"), nullable=False)
    field_definition_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fd_field_definitions.id", ondelete="SET NULL"), nullable=True)
    field_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    field_source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ticket")
    default_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="optional")
    column_span: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    section: Mapped["FdFormLayoutSection"] = relationship("FdFormLayoutSection", back_populates="fields")


from app.models.fd_form_layout_section import FdFormLayoutSection  # noqa: E402
