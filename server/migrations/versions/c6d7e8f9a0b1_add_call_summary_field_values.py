"""add call summary field values

Revision ID: c6d7e8f9a0b1
Revises: 5a6b7c8d9e0f, b3c4d5e6f7a8
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = (
    "5a6b7c8d9e0f",
    "b3c4d5e6f7a8",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_summary_field_values",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.Integer(), nullable=False),
        sa.Column("field_definition_id", sa.Integer(), nullable=True),
        sa.Column("field_key", sa.String(length=64), nullable=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_definition_id"], ["fd_field_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_call_summary_field_values_tenant_call_record",
        "call_summary_field_values",
        ["tenant_id", "call_record_id"],
        unique=False,
    )
    op.create_index(
        "uq_call_summary_values_field_def",
        "call_summary_field_values",
        ["tenant_id", "call_record_id", "field_definition_id"],
        unique=True,
        postgresql_where=sa.text("field_definition_id IS NOT NULL"),
    )
    op.create_index(
        "uq_call_summary_values_field_key",
        "call_summary_field_values",
        ["tenant_id", "call_record_id", "field_key"],
        unique=True,
        postgresql_where=sa.text("field_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_call_summary_values_field_key", table_name="call_summary_field_values")
    op.drop_index("uq_call_summary_values_field_def", table_name="call_summary_field_values")
    op.drop_index("ix_call_summary_field_values_tenant_call_record", table_name="call_summary_field_values")
    op.drop_table("call_summary_field_values")
