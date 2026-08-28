"""add outbound prescreen intents

Revision ID: d7f9a1b3c5e7
Revises: c6e8a0b2d4f6
Create Date: 2026-08-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.vector import Vector


revision: str = "d7f9a1b3c5e7"
down_revision: Union[str, None] = "c6e8a0b2d4f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbound_prescreen_intents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("intent_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "similarity_threshold",
            sa.Numeric(precision=4, scale=3),
            server_default="0.860",
            nullable=False,
        ),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "intent_key", name="uq_outbound_prescreen_intents_tenant_key"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_outbound_prescreen_intents_tenant_name"),
    )
    op.create_index(
        "ix_outbound_prescreen_intents_tenant_enabled",
        "outbound_prescreen_intents",
        ["tenant_id", "enabled"],
    )
    op.create_table(
        "outbound_prescreen_intent_examples",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("intent_id", sa.Integer(), nullable=False),
        sa.Column("example_type", sa.String(length=16), nullable=False),
        sa.Column("text", sa.String(length=50), nullable=False),
        sa.Column("normalized_text", sa.String(length=50), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_status", sa.String(length=16), server_default="ready", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["intent_id"], ["outbound_prescreen_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "intent_id",
            "example_type",
            "normalized_text",
            name="uq_outbound_prescreen_examples_intent_type_text",
        ),
    )
    op.create_index(
        "ix_outbound_prescreen_examples_tenant_intent_type",
        "outbound_prescreen_intent_examples",
        ["tenant_id", "intent_id", "example_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbound_prescreen_examples_tenant_intent_type",
        table_name="outbound_prescreen_intent_examples",
    )
    op.drop_table("outbound_prescreen_intent_examples")
    op.drop_index(
        "ix_outbound_prescreen_intents_tenant_enabled",
        table_name="outbound_prescreen_intents",
    )
    op.drop_table("outbound_prescreen_intents")
