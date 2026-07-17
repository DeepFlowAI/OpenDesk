"""
Call prompt tone schemas — per-tenant customer-facing prompt tones for
hold / consult / three-party / transfer call operations.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


# Scene keys and their fixed defaults (see requirement §1.2).
SCENES: tuple[str, ...] = ("hold", "consult", "three_party", "transfer")

DEFAULT_TTS_TEXT: dict[str, str] = {
    "hold": "通话已保持，请稍候。",
    "consult": "客服正在为您咨询，请稍候。",
    "three_party": "正在邀请其他人员加入通话，请稍候。",
    "transfer": "正在为您转接，请稍候。",
}

# Play mode is fixed in this phase: loop every 15s for hold/consult/three_party,
# single play for transfer. Read-only — surfaced to the client but not editable.
PLAY_MODE: dict[str, str] = {
    "hold": "loop_15s",
    "consult": "loop_15s",
    "three_party": "loop_15s",
    "transfer": "once",
}


class CallPromptTone(BaseModel):
    """One scene's prompt tone configuration."""

    model_config = ConfigDict(from_attributes=True)

    scene: Literal["hold", "consult", "three_party", "transfer"]
    enabled: bool
    prompt_type: Literal["tts", "audio"]
    tts_text: str | None = None
    audio_asset_id: int | None = None
    # Derived, read-only.
    play_mode: Literal["loop_15s", "once"] | None = None

    @model_validator(mode="after")
    def _fill_play_mode(self) -> "CallPromptTone":
        if self.play_mode is None:
            self.play_mode = PLAY_MODE[self.scene]
        return self


class CallPromptToneItemUpdate(BaseModel):
    """Incoming config for a single scene on save."""

    scene: Literal["hold", "consult", "three_party", "transfer"]
    enabled: bool
    prompt_type: Literal["tts", "audio"]
    tts_text: str | None = None
    audio_asset_id: int | None = None


class CallPromptToneSettingsUpdate(BaseModel):
    """Full save payload — all four scenes submitted together."""

    scenes: list[CallPromptToneItemUpdate]


class CallPromptToneSettingsResponse(BaseModel):
    scenes: list[CallPromptTone]


def default_scene(scene: str) -> CallPromptTone:
    """Default configuration for a scene when the tenant has no stored row."""
    return CallPromptTone(
        scene=scene,
        enabled=True,
        prompt_type="tts",
        tts_text=DEFAULT_TTS_TEXT[scene],
        audio_asset_id=None,
    )
