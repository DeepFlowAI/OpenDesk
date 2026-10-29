"""
User model — end users (formerly visitors) who contact support

`name` doubles as the "nickname" system field — SYSTEM_USER_FIELDS key
"nickname" maps to this column so there is no separate nickname column.
"""
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import AuditActorMixin, MetadataMixin, SlotColumnMixin


# Keep the expression literal so prepared queries can use its expression index.
NORMALIZED_PHONE_SQL = r"regexp_replace(regexp_replace(phone, '\D', '', 'g'), '^00', '')"


class User(Base, MetadataMixin, AuditActorMixin, SlotColumnMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_users_tenant_external"),
        UniqueConstraint("public_id", name="uq_users_public_id"),
        Index("ix_users_tenant_id", "tenant_id"),
        Index("ix_users_tenant_normalized_phone", "tenant_id", text(NORMALIZED_PHONE_SQL)),
        Index("ix_users_agent", "agent_id"),
        Index("ix_users_assignee_group", "assignee_group_id"),
        Index(
            "ix_users_tenant_created_id",
            "tenant_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index("ix_users_tenant_organization_id", "tenant_id", "organization_id"),
        Index(
            "ix_users_public_id_trgm",
            "public_id",
            postgresql_using="gin",
            postgresql_ops={"public_id": "gin_trgm_ops"},
        ),
        Index(
            "ix_users_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_users_external_id_trgm",
            "external_id",
            postgresql_using="gin",
            postgresql_ops={"external_id": "gin_trgm_ops"},
        ),
    )

    # ── Core identity ──
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # ── System default fields (§4 of 用户字段模型) ──
    # `name` = nickname (system field key "nickname" → this column)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="normal", server_default="normal")
    address: Mapped[str | None] = mapped_column(String(256), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    web_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    blacklist: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── Associations & meta ──
    avatar_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    assignee_group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employee_groups.id", ondelete="SET NULL"), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
