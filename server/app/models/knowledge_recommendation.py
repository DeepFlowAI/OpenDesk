"""
Knowledge recommendation models.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.configs.settings import settings
from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.vector import Vector


class ConversationUserEmbedding(Base, TimestampMixin):
    __tablename__ = "conversation_user_embeddings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "conversation_id", name="uq_conversation_user_embeddings_tenant_conversation"),
        Index("ix_conversation_user_embeddings_tenant_status", "tenant_id", "embedding_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_message_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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
