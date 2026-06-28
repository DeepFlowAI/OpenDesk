"""
Knowledge base models.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.configs.settings import settings
from app.db.session import Base
from app.models.base import AuditActorMixin, TimestampMixin
from app.models.vector import Vector


class KnowledgeDirectory(Base, TimestampMixin, AuditActorMixin):
    __tablename__ = "knowledge_directories"
    __table_args__ = (
        Index("ix_knowledge_directories_tenant_parent", "tenant_id", "parent_id"),
        Index(
            "uq_knowledge_directories_tenant_root_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
        ),
        Index(
            "uq_knowledge_directories_tenant_parent_name",
            "tenant_id",
            "parent_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("knowledge_directories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class KnowledgeDocument(Base, TimestampMixin, AuditActorMixin):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("ix_knowledge_documents_tenant_directory", "tenant_id", "directory_id"),
        Index("ix_knowledge_documents_tenant_updated", "tenant_id", "updated_at"),
        Index("ix_knowledge_documents_tenant_embedding_status", "tenant_id", "embedding_status"),
        Index(
            "uq_knowledge_documents_tenant_directory_title",
            "tenant_id",
            "directory_id",
            "title",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    directory_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("knowledge_directories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False)
    content_plain: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    validity_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="permanent")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.KNOWLEDGE_EMBEDDING_DIMENSION), nullable=True)
    embedding_model: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=settings.KNOWLEDGE_EMBEDDING_MODEL,
        server_default="text-embedding-v4",
    )
    embedding_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=settings.knowledge_embedding_version,
        server_default="text-embedding-v4:1024",
    )
    embedding_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
