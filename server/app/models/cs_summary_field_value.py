"""
CsSummaryFieldValue model — per-conversation values for conversation minutes
"""
from sqlalchemy import Integer, String, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class CsSummaryFieldValue(Base, TimestampMixin):
    __tablename__ = "cs_summary_field_values"
    __table_args__ = (
        Index("ix_cs_summary_field_values_tenant_conversation", "tenant_id", "conversation_id"),
        Index(
            "uq_cs_summary_values_field_def",
            "tenant_id",
            "conversation_id",
            "field_definition_id",
            unique=True,
            postgresql_where=text("field_definition_id IS NOT NULL"),
        ),
        Index(
            "uq_cs_summary_values_field_key",
            "tenant_id",
            "conversation_id",
            "field_key",
            unique=True,
            postgresql_where=text("field_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False,
    )
    field_definition_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("fd_field_definitions.id", ondelete="CASCADE"), nullable=True,
    )
    field_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value: Mapped[object | None] = mapped_column(JSONB, nullable=True)

    field_definition: Mapped["FdFieldDefinition | None"] = relationship("FdFieldDefinition", lazy="selectin")


from app.models.fd_field_definition import FdFieldDefinition  # noqa: E402
