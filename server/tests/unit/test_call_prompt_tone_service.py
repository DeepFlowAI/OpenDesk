"""
Unit tests for call prompt tone service — defaults + save validation.
"""
import pytest

from app.core.exceptions import ValidationError
from app.repositories.audio_asset_repository import AudioAssetRepository
from app.repositories.call_prompt_tone_repository import CallPromptToneRepository
from app.schemas.call_prompt_tone import (
    DEFAULT_TTS_TEXT,
    PLAY_MODE,
    SCENES,
    CallPromptToneItemUpdate,
    CallPromptToneSettingsUpdate,
)
from app.services.call_prompt_tone_service import CallPromptToneService


def _all_scenes(**overrides) -> CallPromptToneSettingsUpdate:
    """Build a valid full payload; per-scene fields can be overridden by key."""
    items = []
    for scene in SCENES:
        base = {
            "scene": scene,
            "enabled": True,
            "prompt_type": "tts",
            "tts_text": DEFAULT_TTS_TEXT[scene],
            "audio_asset_id": None,
        }
        base.update(overrides.get(scene, {}))
        items.append(CallPromptToneItemUpdate(**base))
    return CallPromptToneSettingsUpdate(scenes=items)


class TestCallPromptToneDefaults:

    @pytest.mark.asyncio
    async def test_get_settings_returns_defaults_when_empty(self, monkeypatch):
        async def fake_list(_db, _tenant_id):
            return []

        monkeypatch.setattr(CallPromptToneRepository, "list_by_tenant", fake_list)

        result = await CallPromptToneService.get_settings(object(), tenant_id=1)

        assert [s.scene for s in result.scenes] == list(SCENES)
        for s in result.scenes:
            assert s.enabled is True
            assert s.prompt_type == "tts"
            assert s.tts_text == DEFAULT_TTS_TEXT[s.scene]
            assert s.play_mode == PLAY_MODE[s.scene]

    @pytest.mark.asyncio
    async def test_transfer_play_mode_is_once(self, monkeypatch):
        async def fake_list(_db, _tenant_id):
            return []

        monkeypatch.setattr(CallPromptToneRepository, "list_by_tenant", fake_list)
        result = await CallPromptToneService.get_settings(object(), tenant_id=1)
        transfer = next(s for s in result.scenes if s.scene == "transfer")
        assert transfer.play_mode == "once"


class TestCallPromptToneSaveValidation:

    @pytest.mark.asyncio
    async def test_enabled_tts_empty_text_rejected(self, monkeypatch):
        payload = _all_scenes(hold={"tts_text": "   "})

        with pytest.raises(ValidationError, match="TTS text"):
            await CallPromptToneService.update_settings(_FakeDb(), 1, payload)

    @pytest.mark.asyncio
    async def test_enabled_tts_too_long_rejected(self, monkeypatch):
        payload = _all_scenes(hold={"tts_text": "x" * 301})

        with pytest.raises(ValidationError, match="TTS text"):
            await CallPromptToneService.update_settings(_FakeDb(), 1, payload)

    @pytest.mark.asyncio
    async def test_enabled_audio_missing_asset_rejected(self, monkeypatch):
        payload = _all_scenes(
            hold={"prompt_type": "audio", "tts_text": None, "audio_asset_id": None}
        )

        with pytest.raises(ValidationError, match="audio file is required"):
            await CallPromptToneService.update_settings(_FakeDb(), 1, payload)

    @pytest.mark.asyncio
    async def test_enabled_audio_invalid_asset_rejected(self, monkeypatch):
        async def fake_exists(_db, _ids, _tenant_id):
            return set()  # asset gone

        monkeypatch.setattr(AudioAssetRepository, "exists_ids", fake_exists)
        payload = _all_scenes(
            hold={"prompt_type": "audio", "tts_text": None, "audio_asset_id": 99}
        )

        with pytest.raises(ValidationError, match="no longer available"):
            await CallPromptToneService.update_settings(_FakeDb(), 1, payload)

    @pytest.mark.asyncio
    async def test_disabled_scene_skips_validation(self, monkeypatch):
        async def fake_exists(_db, _ids, _tenant_id):
            return set()

        upserts: list[tuple[str, dict]] = []

        async def fake_upsert(_db, _tenant_id, scene, data):
            upserts.append((scene, data))
            return object()

        async def fake_get(_db, _tenant_id):
            return "OK"

        monkeypatch.setattr(AudioAssetRepository, "exists_ids", fake_exists)
        monkeypatch.setattr(CallPromptToneRepository, "upsert", fake_upsert)
        monkeypatch.setattr(CallPromptToneService, "get_settings", fake_get)

        # Disabled hold with empty text must NOT raise.
        payload = _all_scenes(hold={"enabled": False, "tts_text": ""})
        result = await CallPromptToneService.update_settings(_FakeDb(), 1, payload)

        assert result == "OK"
        assert len(upserts) == len(SCENES)

    @pytest.mark.asyncio
    async def test_valid_audio_scene_persists_asset_id(self, monkeypatch):
        async def fake_exists(_db, _ids, _tenant_id):
            return {99}

        upserts: dict[str, dict] = {}

        async def fake_upsert(_db, _tenant_id, scene, data):
            upserts[scene] = data
            return object()

        async def fake_get(_db, _tenant_id):
            return "OK"

        monkeypatch.setattr(AudioAssetRepository, "exists_ids", fake_exists)
        monkeypatch.setattr(CallPromptToneRepository, "upsert", fake_upsert)
        monkeypatch.setattr(CallPromptToneService, "get_settings", fake_get)

        payload = _all_scenes(
            hold={"prompt_type": "audio", "tts_text": None, "audio_asset_id": 99}
        )
        await CallPromptToneService.update_settings(_FakeDb(), 1, payload)

        assert upserts["hold"]["audio_asset_id"] == 99
        # A TTS scene should drop any stray audio_asset_id.
        assert upserts["consult"]["audio_asset_id"] is None


class _FakeDb:
    async def commit(self):
        return None
