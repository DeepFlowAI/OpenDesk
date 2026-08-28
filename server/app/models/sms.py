"""
SMS domain models: platform-level signatures/templates, tenant grants and send records.
"""
from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin

SMS_PROVIDER_ALIYUN = "aliyun"

SMS_STATUS_ENABLED = "enabled"
SMS_STATUS_DISABLED = "disabled"

SMS_TEMPLATE_TYPE_NOTIFY = "notify"
SMS_TEMPLATE_TYPE_PROMO = "promo"

SMS_SEND_STATUS_PENDING = "pending"
SMS_SEND_STATUS_SUBMITTED = "submitted"
SMS_SEND_STATUS_DELIVERED = "delivered"
SMS_SEND_STATUS_FAILED = "failed"

SMS_SEND_SOURCE_SINGLE = "single"
SMS_SEND_SOURCE_BULK = "bulk"


class SmsSignature(Base, TimestampMixin):
    """Platform-level SMS signature bound to a provider-side approved sign name."""

    __tablename__ = "sms_signatures"
    __table_args__ = (
        Index(
            "uq_sms_signatures_enabled_provider_sign",
            "provider",
            "provider_sign_name",
            unique=True,
            postgresql_where="status = 'enabled'",
        ),
        Index("ix_sms_signatures_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_sign_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SMS_STATUS_ENABLED, server_default=SMS_STATUS_ENABLED)


class SmsTemplate(Base, TimestampMixin):
    """Platform-level SMS template with variable definitions and channel binding."""

    __tablename__ = "sms_templates"
    __table_args__ = (
        UniqueConstraint("provider", "provider_template_code", name="uq_sms_templates_provider_code"),
        Index("ix_sms_templates_status", "status"),
        Index("ix_sms_templates_signature_id", "signature_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default=SMS_TEMPLATE_TYPE_NOTIFY, server_default=SMS_TEMPLATE_TYPE_NOTIFY)
    signature_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sms_signatures.id", ondelete="RESTRICT"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    variables: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SMS_STATUS_ENABLED, server_default=SMS_STATUS_ENABLED)


class SmsTemplateGrant(Base, TimestampMixin):
    """Authorization of a platform template to a tenant."""

    __tablename__ = "sms_template_grants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "template_id", name="uq_sms_template_grants_tenant_template"),
        Index("ix_sms_template_grants_template_id", "template_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sms_templates.id", ondelete="CASCADE"),
        nullable=False,
    )


class SmsSendRecord(Base, TimestampMixin):
    """One single-send SMS business record with full snapshots."""

    __tablename__ = "sms_send_records"
    __table_args__ = (
        Index(
            "uq_sms_send_records_client_request",
            "tenant_id",
            "client_request_id",
            unique=True,
            postgresql_where="client_request_id IS NOT NULL",
        ),
        Index("ix_sms_send_records_tenant_created", "tenant_id", "created_at"),
        Index("ix_sms_send_records_tenant_phone", "tenant_id", "phone"),
        Index("ix_sms_send_records_tenant_status", "tenant_id", "status"),
        Index("ix_sms_send_records_provider_biz_id", "provider", "provider_biz_id"),
        Index("ix_sms_send_records_tenant_source", "tenant_id", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sms_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_name: Mapped[str] = mapped_column(String(64), nullable=False)
    template_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sign_name: Mapped[str] = mapped_column(String(64), nullable=False)
    body_snapshot: Mapped[str] = mapped_column(String(600), nullable=False)
    variables_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SMS_SEND_STATUS_PENDING, server_default=SMS_SEND_STATUS_PENDING)
    fail_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SMS_SEND_SOURCE_SINGLE, server_default=SMS_SEND_SOURCE_SINGLE
    )
    bulk_task_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sms_bulk_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    call_record_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("call_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_biz_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
