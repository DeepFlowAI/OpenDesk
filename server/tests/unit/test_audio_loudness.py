"""Upload-time loudness leveling: unhealthy prompts are leveled to the
playback target loudness, healthy/silent/undecodable uploads pass through
byte-for-byte, and leveling failures never fail an upload."""
from __future__ import annotations

import io
import math
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.services import audio_asset_service as svc_mod
from app.services import audio_loudness
from app.services.audio_asset_service import AudioAssetService

RATE = audio_loudness.TARGET_SAMPLE_RATE
FRAME = audio_loudness.FRAME_SAMPLES


def _sine_pcm(rms: float, seconds: float = 2.0, freq: float = 440.0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    amp = rms * math.sqrt(2)
    return np.rint(amp * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def _square_pcm(amplitude: float, seconds: float = 2.0, freq: float = 440.0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return np.rint(amplitude * np.sign(np.sin(2 * np.pi * freq * t))).astype(np.int16)


def _wav_bytes(pcm: np.ndarray, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.astype("<i2").tobytes())
    return buf.getvalue()


def _read_wav(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data)) as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == RATE
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype="<i2").copy()


def _voiced_median_rms(pcm: np.ndarray) -> float:
    frame = audio_loudness.FRAME_SAMPLES
    values = np.abs(pcm.astype(np.float64))
    rms = [
        math.sqrt(np.dot(values[s : s + frame], values[s : s + frame]) / len(values[s : s + frame]))
        for s in range(0, pcm.size, frame)
    ]
    voiced = sorted(r for r in rms if r >= audio_loudness.NOISE_RMS)
    return voiced[len(voiced) // 2]


class _FakeSessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        return False


def _patch_upload(monkeypatch) -> dict:
    """Stub storage + DB around upload_managed; returns captured storage write."""

    stored: dict = {}
    storage = MagicMock()

    async def _upload(key, data, content_type=None):
        stored["key"] = key
        stored["data"] = data
        stored["content_type"] = content_type

    storage.upload = _upload
    storage.get_temporary_url = AsyncMock(return_value="https://example.com/preview")
    monkeypatch.setattr(svc_mod, "create_storage_client", lambda: storage)
    monkeypatch.setattr(
        svc_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx(MagicMock())
    )
    monkeypatch.setattr(
        svc_mod.AuditActorService,
        "resolve_current_employee",
        AsyncMock(return_value={"actor_type": "employee", "actor_id": 1, "actor_name": "t"}),
    )

    async def _create(db, data):
        return SimpleNamespace(
            id=1,
            name=data["name"],
            mime_type=data["mime_type"],
            size_bytes=data["size_bytes"],
            duration_ms=data["duration_ms"],
            created_at=None,
        )

    monkeypatch.setattr(svc_mod.AudioAssetRepository, "create", _create)
    return stored


# ─────────────── Pure leveling (parity with the playback-side algorithm) ────


def test_level_quiet_prompt_boosted_toward_target():
    pcm = _sine_pcm(rms=800.0)
    out = audio_loudness.level_speech_for_playback(pcm)
    assert out is not pcm
    assert out.size == pcm.size  # timing unchanged
    assert abs(_voiced_median_rms(out) - audio_loudness.TARGET_RMS) < 100
    # One scalar gain (derived from the voiced median) for the whole clip —
    # only rounding deviates.
    gain = audio_loudness.TARGET_RMS / _voiced_median_rms(pcm)
    assert np.allclose(out, pcm * gain, atol=1)


def test_level_loud_prompt_compressed_toward_target():
    pcm = _sine_pcm(rms=15000.0)
    out = audio_loudness.level_speech_for_playback(pcm)
    assert out is not pcm
    assert abs(_voiced_median_rms(out) - audio_loudness.TARGET_RMS) < 100
    assert np.abs(out.astype(np.int32)).max() <= audio_loudness.PEAK_CEILING


def test_level_clipped_prompt_scaled_below_ceiling():
    # Median loudness is healthy, but enough frames sit at full scale that
    # the robust (p95) frame peak exceeds the ceiling.
    pcm = _sine_pcm(rms=5000.0)
    for f in range(0, 100, 10):
        pcm[f * FRAME] = 30000  # 10 of 100 frames peaked → p95 = 30000
    out = audio_loudness.level_speech_for_playback(pcm)
    assert out is not pcm
    # Gain = min(5500/5000, 29204/30000) < 1 — peak capped, not boosted.
    assert np.abs(out.astype(np.int32)).max() <= audio_loudness.PEAK_CEILING
    assert out[0] < 30000
    assert np.allclose(out, pcm * (audio_loudness.PEAK_CEILING / 30000.0), atol=1)


def test_full_scale_spikes_with_healthy_median_pass_through():
    # Median ~1800, p95 frame peak ~25000, one absolute-max sample (32766):
    # the abs max is over the ceiling but the robust peak is not — ordinary
    # spiky recordings must pass through untouched.
    pcm = _sine_pcm(rms=1800.0)
    for f in range(0, 100, 10):
        pcm[f * FRAME] = 25000  # 10 frames peaked at 25000 → p95 = 25000
    pcm[95 * FRAME + 1] = 32766
    assert audio_loudness.level_speech_for_playback(pcm) is pcm


def test_uniform_quiet_prompt_boost_not_capped_by_frame_peak():
    # Uniform quiet asset with frame peaks ~4000: the peak cap
    # (29204/4000 ≈ 7.3) must not interfere with the ≈5500/800 boost.
    pcm = _square_pcm(amplitude=769.0)
    pcm[::FRAME] = 4000  # one spike per frame → frame RMS ~800, peak 4000
    out = audio_loudness.level_speech_for_playback(pcm)
    assert out is not pcm
    gain = audio_loudness.TARGET_RMS / _voiced_median_rms(pcm)
    assert gain < audio_loudness.PEAK_CEILING / 4000.0
    assert np.allclose(out, pcm * gain, atol=1)
    assert abs(_voiced_median_rms(out) - audio_loudness.TARGET_RMS) < 100


def test_spiky_quiet_prompt_boost_capped_by_robust_peak_not_absmax():
    # Median ~800, p95 frame peak ~24000, one absolute-max sample: the boost
    # is capped at 29204/24000 ≈ 1.22 (still a boost) — not at
    # 29204/32766 ≈ 0.89, which would make the asset even quieter.
    pcm = _sine_pcm(rms=800.0)
    for f in range(90, 99):
        pcm[f * FRAME] = 24000  # p95 frame peak = 24000
    pcm[99 * FRAME] = 32766     # absolute max
    out = audio_loudness.level_speech_for_playback(pcm)
    assert out is not pcm
    expected_gain = audio_loudness.PEAK_CEILING / 24000.0
    assert expected_gain > 1.0
    normal = np.arange(pcm.size) < 90 * FRAME
    assert np.allclose(out[normal], pcm[normal] * expected_gain, atol=1)
    # The top spike frame ends up lightly clipped at the ceiling.
    assert out[99 * FRAME] == int(audio_loudness.PEAK_CEILING)


def test_level_dynamic_but_healthy_median_passes_through():
    # Regression: wide internal dynamics (p90/p10 ~ 19x) with a healthy
    # median must pass through — leveling must not flatten dynamics.
    quiet = _sine_pcm(rms=100.0, seconds=0.3)    # 15 frames
    normal = _sine_pcm(rms=1900.0, seconds=1.7)  # 85 frames
    pcm = np.concatenate([quiet, normal])
    assert audio_loudness.level_speech_for_playback(pcm) is pcm


def test_level_healthy_prompt_returned_unchanged():
    pcm = _sine_pcm(rms=5000.0)
    assert audio_loudness.level_speech_for_playback(pcm) is pcm


def test_level_silence_returned_unchanged():
    pcm = np.zeros(RATE * 2, dtype=np.int16)
    assert audio_loudness.level_speech_for_playback(pcm) is pcm


# ─────────────── Upload flow ───────────────


@pytest.mark.asyncio
async def test_upload_quiet_wav_is_leveled_and_stored_as_wav(monkeypatch):
    stored = _patch_upload(monkeypatch)
    original = _wav_bytes(_sine_pcm(rms=800.0))

    payload = await AudioAssetService.upload_managed(
        1, 1, filename="quiet.wav", content_type="audio/wav", data=original
    )

    assert stored["data"] != original
    assert stored["key"].endswith(".wav")
    assert stored["content_type"] == "audio/wav"
    leveled = _read_wav(stored["data"])
    assert abs(_voiced_median_rms(leveled) - audio_loudness.TARGET_RMS) < 100
    assert payload["mime_type"] == "audio/wav"
    assert payload["size_bytes"] == len(stored["data"])
    assert payload["duration_ms"] == 2000


@pytest.mark.asyncio
async def test_upload_healthy_wav_passes_through_byte_for_byte(monkeypatch):
    stored = _patch_upload(monkeypatch)
    original = _wav_bytes(_sine_pcm(rms=5000.0))

    payload = await AudioAssetService.upload_managed(
        1, 1, filename="ok.wav", content_type="audio/wav", data=original
    )

    assert stored["data"] == original
    assert payload["duration_ms"] is None


@pytest.mark.asyncio
async def test_upload_silent_wav_passes_through(monkeypatch):
    stored = _patch_upload(monkeypatch)
    original = _wav_bytes(np.zeros(RATE * 2, dtype=np.int16))

    await AudioAssetService.upload_managed(
        1, 1, filename="silence.wav", content_type="audio/wav", data=original
    )

    assert stored["data"] == original


@pytest.mark.asyncio
async def test_upload_undecodable_mp3_passes_through(monkeypatch):
    stored = _patch_upload(monkeypatch)
    # Sniffs as mp3 (ID3 tag) but holds no decodable frames.
    original = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 200

    payload = await AudioAssetService.upload_managed(
        1, 1, filename="broken.mp3", content_type="audio/mpeg", data=original
    )

    assert stored["data"] == original
    assert stored["key"].endswith(".mp3")
    assert payload["mime_type"] == "audio/mpeg"


@pytest.mark.asyncio
async def test_upload_still_succeeds_when_leveling_raises(monkeypatch):
    stored = _patch_upload(monkeypatch)

    def _boom(data, kind):
        raise RuntimeError("unexpected decoder bug")

    monkeypatch.setattr(svc_mod.audio_loudness, "normalize_for_upload", _boom)
    original = _wav_bytes(_sine_pcm(rms=800.0))

    payload = await AudioAssetService.upload_managed(
        1, 1, filename="quiet.wav", content_type="audio/wav", data=original
    )

    assert stored["data"] == original
    assert payload["mime_type"] == "audio/wav"
