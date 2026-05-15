"""
FdFieldDefinition model — unified field definition for all domains
"""
from sqlalchemy import (
    Boolean, Integer, String, Text, ForeignKey,
    Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class FdFieldDefinition(Base, TimestampMixin):
    __tablename__ = "fd_field_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", "name", name="uq_fd_field_defs_tenant_domain_name"),
        UniqueConstraint("tenant_id", "domain", "field_key", name="uq_fd_field_defs_tenant_domain_field_key"),
        Index("ix_fd_field_defs_tenant_domain", "tenant_id", "domain"),
        Index("ix_fd_field_defs_tenant_domain_status", "tenant_id", "domain", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="custom")
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_type: Mapped[str] = mapped_column(String(32), nullable=False)
    type_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    slot_column: Mapped[str] = mapped_column(String(16), nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    applicable_modules: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    show_in_workspace: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Relationships
    options: Mapped[list["FdFieldOption"]] = relationship(
        "FdFieldOption", back_populates="field_definition",
        cascade="all, delete-orphan", lazy="selectin",
    )
    tree_nodes: Mapped[list["FdTreeNode"]] = relationship(
        "FdTreeNode", back_populates="field_definition",
        cascade="all, delete-orphan", lazy="selectin",
    )

    @property
    def key(self) -> str:
        """Alias for API / Pydantic (`FdFieldDefinitionResponse.key`)."""
        return self.field_key


from app.models.fd_field_option import FdFieldOption  # noqa: E402
from app.models.fd_tree_node import FdTreeNode  # noqa: E402
