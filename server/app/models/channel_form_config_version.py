"""Immutable Web SDK form-message configuration versions."""

from sqlalchemy import ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ChannelFormConfigVersion(Base, TimestampMixin):
    __tablename__ = "channel_form_config_versions"
    __table_args__ = (
        UniqueConstraint("channel_id", "version", name="uq_channel_form_config_versions_channel_version"),
        Index(
            "ix_channel_form_config_versions_tenant_channel_version",
            "tenant_id",
            "channel_id",
            "version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
