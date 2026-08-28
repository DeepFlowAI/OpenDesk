"""add sms single send tables

Revision ID: b7c8d9e0f1a2
Revises: e9f0a1b2c3d4, f1a2b3c4d5e6
Create Date: 2026-08-07 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = ("e9f0a1b2c3d4", "f1a2b3c4d5e6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sms_signatures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_sign_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="enabled", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_sms_signatures_enabled_provider_sign",
        "sms_signatures",
        ["provider", "provider_sign_name"],
        unique=True,
        postgresql_where=sa.text("status = 'enabled'"),
    )
    op.create_index("ix_sms_signatures_status", "sms_signatures", ["status"], unique=False)

    op.create_table(
        "sms_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=16), server_default="notify", nullable=False),
        sa.Column("signature_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_template_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="enabled", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["signature_id"], ["sms_signatures.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_template_code", name="uq_sms_templates_provider_code"),
    )
    op.create_index("ix_sms_templates_status", "sms_templates", ["status"], unique=False)
    op.create_index("ix_sms_templates_signature_id", "sms_templates", ["signature_id"], unique=False)

    op.create_table(
        "sms_template_grants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["sms_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "template_id", name="uq_sms_template_grants_tenant_template"),
    )
    op.create_index("ix_sms_template_grants_tenant_id", "sms_template_grants", ["tenant_id"], unique=False)
    op.create_index("ix_sms_template_grants_template_id", "sms_template_grants", ["template_id"], unique=False)

    op.create_table(
        "sms_send_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("template_name", sa.String(length=64), nullable=False),
        sa.Column("template_type", sa.String(length=16), nullable=False),
        sa.Column("sign_name", sa.String(length=64), nullable=False),
        sa.Column("body_snapshot", sa.String(length=600), nullable=False),
        sa.Column("variables_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("fail_reason", sa.String(length=255), nullable=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_biz_id", sa.String(length=128), nullable=True),
        sa.Column("client_request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["sms_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_sms_send_records_client_request",
        "sms_send_records",
        ["tenant_id", "client_request_id"],
        unique=True,
        postgresql_where=sa.text("client_request_id IS NOT NULL"),
    )
    op.create_index("ix_sms_send_records_tenant_created", "sms_send_records", ["tenant_id", "created_at"], unique=False)
    op.create_index("ix_sms_send_records_tenant_phone", "sms_send_records", ["tenant_id", "phone"], unique=False)
    op.create_index("ix_sms_send_records_tenant_status", "sms_send_records", ["tenant_id", "status"], unique=False)
    op.create_index("ix_sms_send_records_provider_biz_id", "sms_send_records", ["provider", "provider_biz_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sms_send_records_provider_biz_id", table_name="sms_send_records")
    op.drop_index("ix_sms_send_records_tenant_status", table_name="sms_send_records")
    op.drop_index("ix_sms_send_records_tenant_phone", table_name="sms_send_records")
    op.drop_index("ix_sms_send_records_tenant_created", table_name="sms_send_records")
    op.drop_index("uq_sms_send_records_client_request", table_name="sms_send_records")
    op.drop_table("sms_send_records")
    op.drop_index("ix_sms_template_grants_template_id", table_name="sms_template_grants")
    op.drop_index("ix_sms_template_grants_tenant_id", table_name="sms_template_grants")
    op.drop_table("sms_template_grants")
    op.drop_index("ix_sms_templates_signature_id", table_name="sms_templates")
    op.drop_index("ix_sms_templates_status", table_name="sms_templates")
    op.drop_table("sms_templates")
    op.drop_index("ix_sms_signatures_status", table_name="sms_signatures")
    op.drop_index("uq_sms_signatures_enabled_provider_sign", table_name="sms_signatures")
    op.drop_table("sms_signatures")
