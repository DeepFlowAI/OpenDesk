"""add knowledge document attachments

Revision ID: 33c556e0b889
Revises: 22b445d9a778
Create Date: 2026-07-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "33c556e0b889"
down_revision: Union[str, None] = "22b445d9a778"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_document_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column(
            "mime_type",
            sa.String(length=255),
            server_default="application/octet-stream",
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("created_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("created_by_actor_name", sa.String(length=128), nullable=True),
        sa.Column("updated_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("updated_by_actor_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_actor_name", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_knowledge_doc_attachment_storage_key"),
    )
    op.create_index(
        "ix_knowledge_doc_attachment_document_order",
        "knowledge_document_attachments",
        ["document_id", "sort_order"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_doc_attachment_tenant_expiry",
        "knowledge_document_attachments",
        ["tenant_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_doc_attachment_tenant_expiry",
        table_name="knowledge_document_attachments",
    )
    op.drop_index(
        "ix_knowledge_doc_attachment_document_order",
        table_name="knowledge_document_attachments",
    )
    op.drop_table("knowledge_document_attachments")
