"""
CallPromptToneSettings — per-tenant, per-scene customer-facing call prompt tones.

Stores what OpenDesk plays to the customer leg during hold, consultation,
three-party invite and blind-transfer operations. One row per (tenant, scene).

Runtime playback (playing to the customer leg, 15s looping, stop-before-play on
stage change, default-TTS fallback) is performed by the voice kernel, which
consumes this configuration during a live call. This table only persists the
configuration; it does not play audio.
"""
from sqlalchemy import Boolean, Integer, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class CallPromptToneSettings(Base, TimestampMixin):
    __tablename__ = "call_prompt_tone_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scene", name="uq_call_prompt_tone_tenant_scene"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # scene: one of hold | consult | three_party | transfer
    scene: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # prompt_type: tts | audio
    prompt_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="tts")
    tts_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_asset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("audio_assets.id", ondelete="SET NULL"), nullable=True
    )
