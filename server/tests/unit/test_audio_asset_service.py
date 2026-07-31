"""Audio upload must sniff real containers (reject M4A renamed as .mp3)."""
from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.services.audio_asset_service import (
    AudioAssetService,
    detect_playable_audio_kind,
)


def test_detect_wav_and_mp3():
    wav = b"RIFF....WAVE" + b"\x00" * 20
    assert detect_playable_audio_kind(wav) == "wav"
    assert detect_playable_audio_kind(b"ID3" + b"\x00" * 20) == "mp3"
    assert detect_playable_audio_kind(bytes([0xFF, 0xFB]) + b"\x00" * 20) == "mp3"


def test_detect_rejects_m4a_ftyp():
    # Real phone "mp3" that is actually M4A/AAC
    m4a = b"\x00\x00\x00\x1cftypM4A " + b"\x00" * 32
    assert detect_playable_audio_kind(m4a) is None


@pytest.mark.asyncio
async def test_upload_rejects_m4a_disguised_as_mp3(monkeypatch):
    m4a = b"\x00\x00\x00\x1cftypM4A " + b"\x00" * 32
    with pytest.raises(ValidationError) as ei:
        await AudioAssetService.upload(
            db=None,  # type: ignore[arg-type]
            tenant_id=1,
            actor={"actor_type": "employee", "actor_id": 1, "actor_name": "t"},
            filename="这是一个音频文件哈哈.mp3",
            content_type="audio/mpeg",
            data=m4a,
        )
    assert "M4A" in ei.value.message or "AAC" in ei.value.message
    assert "MP3" in ei.value.message or "WAV" in ei.value.message
