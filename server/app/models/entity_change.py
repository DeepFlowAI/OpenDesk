"""
EntityChange model — field-level audit trail for user and organization updates.
"""
from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class EntityChange(Base, TimestampMixin):
    __tablename__ = "entity_changes"
    __table_args__ = (
        Index(
            "ix_entity_changes_tenant_entity_created",
            "tenant_id",
            "entity_type",
            "entity_id",
            "created_at",
        ),
        Index("ix_entity_changes_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="user")
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    field_label: Mapped[str] = mapped_column(String(128), nullable=False)
    field_source: Mapped[str] = mapped_column(String(32), nullable=False)
    old_value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
