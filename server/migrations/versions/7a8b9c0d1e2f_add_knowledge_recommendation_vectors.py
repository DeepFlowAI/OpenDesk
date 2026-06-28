"""add knowledge recommendation vectors

Revision ID: 7a8b9c0d1e2f
Revises: 6e7f8a9b0c1d
Create Date: 2026-06-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "6e7f8a9b0c1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                BEGIN
                    CREATE EXTENSION vector;
                EXCEPTION
                    WHEN insufficient_privilege THEN
                        RAISE EXCEPTION
                            'pgvector extension is available but not installed. Install extension "vector" with a privileged database user before running this migration.';
                END;
            END IF;
        END $$;
        """
    )

    op.add_column(
        "knowledge_documents",
        sa.Column("embedding_model", sa.String(length=64), server_default="text-embedding-v4", nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("embedding_version", sa.String(length=32), server_default="text-embedding-v4:1024", nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("embedding_status", sa.String(length=16), server_default="pending", nullable=False),
    )
    op.add_column("knowledge_documents", sa.Column("embedding_error", sa.Text(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("ALTER TABLE knowledge_documents ADD COLUMN embedding vector(1024)")
    op.create_index(
        "ix_knowledge_documents_tenant_embedding_status",
        "knowledge_documents",
        ["tenant_id", "embedding_status"],
    )

    op.create_table(
        "conversation_user_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("source_message_id", sa.Integer(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=64), server_default="text-embedding-v4", nullable=False),
        sa.Column("embedding_version", sa.String(length=32), server_default="text-embedding-v4:1024", nullable=False),
        sa.Column("embedding_status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("embedding_error", sa.Text(), nullable=True),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "conversation_id", name="uq_conversation_user_embeddings_tenant_conversation"),
    )
    op.execute("ALTER TABLE conversation_user_embeddings ADD COLUMN embedding vector(1024)")
    op.create_index(
        "ix_conversation_user_embeddings_tenant_status",
        "conversation_user_embeddings",
        ["tenant_id", "embedding_status"],
    )

    op.execute(
        """
        DO $$
        BEGIN
            CREATE INDEX ix_knowledge_documents_embedding_hnsw
            ON knowledge_documents
            USING hnsw (embedding vector_cosine_ops)
            WHERE embedding IS NOT NULL;
        EXCEPTION
            WHEN undefined_object OR invalid_parameter_value THEN
                CREATE INDEX ix_knowledge_documents_embedding_hnsw
                ON knowledge_documents
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                WHERE embedding IS NOT NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_embedding_hnsw", table_name="knowledge_documents")
    op.drop_index("ix_conversation_user_embeddings_tenant_status", table_name="conversation_user_embeddings")
    op.drop_table("conversation_user_embeddings")
    op.drop_index("ix_knowledge_documents_tenant_embedding_status", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "embedding")
    op.drop_column("knowledge_documents", "embedded_at")
    op.drop_column("knowledge_documents", "embedding_error")
    op.drop_column("knowledge_documents", "embedding_status")
    op.drop_column("knowledge_documents", "embedding_version")
    op.drop_column("knowledge_documents", "embedding_model")
