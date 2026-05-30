"""
VoiceFlowSystemVariable — global seed table of `sys.*` variables that are
available in every voice flow's condition / reference popup.

Tenant-agnostic — same set for all tenants. Seeded via
server/migrations/sql/v1.6_seed_voice_flow_system_variables.sql.
"""
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class VoiceFlowSystemVariable(Base):
    __tablename__ = "voice_flow_system_variables"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name_en: Mapped[str] = mapped_column(String(64), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    description_zh: Mapped[str] = mapped_column(Text, nullable=False)
    description_en: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
