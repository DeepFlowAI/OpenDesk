"""
Organization model — contact company / organization linked to visitors
"""
from sqlalchemy import String, Integer, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import AuditActorMixin, MetadataMixin, SlotColumnMixin


class Organization(Base, MetadataMixin, AuditActorMixin, SlotColumnMixin):
    __tablename__ = "organizations"
    __table_args__ = (
        Index("ix_organizations_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
