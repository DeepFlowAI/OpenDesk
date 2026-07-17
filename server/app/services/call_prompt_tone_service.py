"""
Call prompt tone service — read/save per-tenant customer-facing prompt tones.

Persists configuration only. Runtime playback to the customer leg (15s looping,
stop-before-play on stage change, default-TTS fallback) is executed by the voice
kernel while a call is in progress, reading this configuration.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.db.session import AsyncSessionLocal
from app.repositories.audio_asset_repository import AudioAssetRepository
from app.repositories.call_prompt_tone_repository import CallPromptToneRepository
from app.schemas.call_prompt_tone import (
    SCENES,
    CallPromptTone,
    CallPromptToneSettingsResponse,
    CallPromptToneSettingsUpdate,
    default_scene,
)

TTS_MIN_LEN = 1
TTS_MAX_LEN = 300


class CallPromptToneService:

    @staticmethod
    async def get_settings(
        db: AsyncSession, tenant_id: int
    ) -> CallPromptToneSettingsResponse:
        """Return all four scenes, filling defaults for any not yet stored."""
        rows = await CallPromptToneRepository.list_by_tenant(db, tenant_id)
        stored = {row.scene: row for row in rows if row.scene in SCENES}

        scenes: list[CallPromptTone] = []
        for scene in SCENES:
            row = stored.get(scene)
            if row is None:
                scenes.append(default_scene(scene))
            else:
                scenes.append(CallPromptTone.model_validate(row))
        return CallPromptToneSettingsResponse(scenes=scenes)

    @staticmethod
    async def update_settings(
        db: AsyncSession, tenant_id: int, data: CallPromptToneSettingsUpdate
    ) -> CallPromptToneSettingsResponse:
        """Validate all enabled scenes, then upsert every submitted scene."""
        by_scene = {item.scene: item for item in data.scenes}
        missing = [s for s in SCENES if s not in by_scene]
        if missing:
            raise ValidationError(f"Missing scenes: {', '.join(missing)}")

        # Collect audio asset ids that need an existence check (enabled + audio).
        asset_ids = [
            item.audio_asset_id
            for item in data.scenes
            if item.enabled and item.prompt_type == "audio" and item.audio_asset_id
        ]
        valid_ids = (
            await AudioAssetRepository.exists_ids(db, asset_ids, tenant_id)
            if asset_ids
            else set()
        )

        for scene in SCENES:
            item = by_scene[scene]
            if item.enabled:
                if item.prompt_type == "tts":
                    text = (item.tts_text or "").strip()
                    if not (TTS_MIN_LEN <= len(text) <= TTS_MAX_LEN):
                        raise ValidationError(
                            f"Scene '{scene}': TTS text must be 1-300 characters"
                        )
                else:  # audio
                    if not item.audio_asset_id:
                        raise ValidationError(
                            f"Scene '{scene}': audio file is required"
                        )
                    if item.audio_asset_id not in valid_ids:
                        raise ValidationError(
                            f"Scene '{scene}': selected audio asset is no longer available"
                        )

            await CallPromptToneRepository.upsert(
                db,
                tenant_id,
                scene,
                {
                    "enabled": item.enabled,
                    "prompt_type": item.prompt_type,
                    "tts_text": item.tts_text,
                    "audio_asset_id": (
                        item.audio_asset_id if item.prompt_type == "audio" else None
                    ),
                },
            )

        await db.commit()
        return await CallPromptToneService.get_settings(db, tenant_id)

    @staticmethod
    async def get_settings_managed(tenant_id: int) -> CallPromptToneSettingsResponse:
        """Read a tenant's prompt tones with a self-contained short session.

        FLOWKIT GAP: internal read point for the voice kernel. The kernel calls
        this (directly or via an internal endpoint) at call time to obtain the
        current per-scene configuration, then performs the actual customer-leg
        playback, looping and default-TTS fallback itself. This repo only stores
        and returns configuration; it never plays audio.
        """
        async with AsyncSessionLocal() as db:
            return await CallPromptToneService.get_settings(db, tenant_id)
