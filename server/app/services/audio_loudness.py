"""
Upload-time loudness leveling for voice-flow audio prompts.

User-uploaded prompts vary wildly in loudness; quiet or clipped audio sounds
bad on the far end after carrier-side G.711→AMR transcoding. This module
levels unhealthy assets toward a target loudness at upload time so the
stored file is what callers actually hear.

``level_speech_for_playback`` mirrors the FlowKit playback-side leveling
(``LevelSpeechForPlayback``): the same frame stats, thresholds, and gain
rule, so the upload gate and the playback fallback classify the same asset
the same way. Leveling applies one scalar gain to the whole clip — it only
corrects overall loudness and clipping, preserving the internal dynamics of
the speech. Health and the gain cap use a robust peak (p95 of per-frame
peaks across voiced frames) instead of the absolute maximum: real assets
often pair a quiet median with a few near-full-scale spike frames, and an
absolute peak would both cap the boost below 1 and misread ordinary
full-scale recordings as clipped. The tradeoff is that those top spike
frames may end up lightly clipped — they already sit near full scale. Keep
the constants and logic in sync with that implementation.
"""
import io
import logging
import math
import wave

import miniaudio
import numpy as np

logger = logging.getLogger(__name__)

# Constants mirrored from the FlowKit playback-side leveling — do not tune
# here without changing the playback fallback in the same way.
TARGET_SAMPLE_RATE = 16000
FRAME_SAMPLES = TARGET_SAMPLE_RATE // 50  # 20ms frames
NOISE_RMS = 32.0
TARGET_RMS = 5500.0
MIN_GAIN = 0.25
MAX_GAIN = 32.0
PEAK_CEILING = 29204.0
HEALTHY_MIN_RMS = 1200.0
HEALTHY_MAX_RMS = 9000.0


def normalize_for_upload(data: bytes, kind: str) -> tuple[bytes, int] | None:
    """Level an uploaded prompt when its speech is unhealthy.

    Returns ``(wav_bytes, duration_ms)`` — a 16kHz mono 16-bit WAV — when the
    audio was leveled, or ``None`` when the original bytes should be stored
    unchanged (healthy audio, pure silence, or anything that cannot be
    decoded as PCM16 wav/mp3).
    """

    pcm = _decode_to_pcm16(data, kind)
    if pcm is None or pcm.size == 0:
        return None
    leveled = level_speech_for_playback(pcm)
    if leveled is pcm:
        return None
    duration_ms = int(round(leveled.size / TARGET_SAMPLE_RATE * 1000))
    return _encode_wav(leveled), duration_ms


def level_speech_for_playback(pcm: np.ndarray) -> np.ndarray:
    """Scale quiet/loud/clipped speech toward ``TARGET_RMS`` with one gain.

    Healthy speech and pure silence are returned unchanged (same object).
    The output always keeps the original sample count and timing.
    """

    if pcm.size == 0:
        return pcm
    rms, peak = _frame_levels(pcm)
    if _is_healthy(rms, peak):
        return pcm

    voiced = rms >= NOISE_RMS
    voiced_rms = np.sort(rms[voiced])
    voiced_median = voiced_rms[voiced_rms.size // 2]
    gain = min(MAX_GAIN, max(MIN_GAIN, TARGET_RMS / voiced_median))
    robust_peak = _robust_peak(peak[voiced])
    if robust_peak > 0:
        gain = min(gain, PEAK_CEILING / robust_peak)

    values = _round_half_away(pcm.astype(np.float64) * gain)
    return np.clip(values, -PEAK_CEILING, PEAK_CEILING).astype(np.int16)


def _frame_levels(pcm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-frame (20ms) RMS and peak, computed on float64 magnitudes."""

    values = np.abs(pcm.astype(np.float64))
    n_frames = (pcm.size + FRAME_SAMPLES - 1) // FRAME_SAMPLES
    rms = np.empty(n_frames)
    peak = np.empty(n_frames)
    for i in range(n_frames):
        frame = values[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]
        rms[i] = math.sqrt(np.dot(frame, frame) / frame.size)
        peak[i] = frame.max()
    return rms, peak


def _is_healthy(rms: np.ndarray, peak: np.ndarray) -> bool:
    voiced = rms >= NOISE_RMS
    if not voiced.any():
        return True
    voiced_rms = np.sort(rms[voiced])
    median = voiced_rms[voiced_rms.size // 2]
    return (
        HEALTHY_MIN_RMS <= median <= HEALTHY_MAX_RMS
        and _robust_peak(peak[voiced]) <= PEAK_CEILING
    )


def _robust_peak(voiced_peaks: np.ndarray) -> float:
    """p95 of per-frame peaks across voiced frames (integer-index style)."""

    if voiced_peaks.size == 0:
        return 0.0
    ordered = np.sort(voiced_peaks)
    return float(ordered[(ordered.size - 1) * 95 // 100])


def _round_half_away(values: np.ndarray) -> np.ndarray:
    """Round half away from zero, matching Go's ``math.Round``."""

    return np.sign(values) * np.floor(np.abs(values) + 0.5)


def _decode_to_pcm16(data: bytes, kind: str) -> np.ndarray | None:
    """Decode to 16kHz mono int16 PCM; ``None`` when undecodable."""

    if kind == "wav":
        return _decode_wav(data)
    if kind == "mp3":
        return _decode_mp3(data)
    return None


def _decode_wav(data: bytes) -> np.ndarray | None:
    """Decode a PCM16 WAV with stdlib only; anything else returns ``None``."""

    try:
        with wave.open(io.BytesIO(data)) as wf:
            if wf.getcomptype() != "NONE" or wf.getsampwidth() != 2:
                return None
            channels = wf.getnchannels()
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
    except (wave.Error, EOFError):
        return None
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != TARGET_SAMPLE_RATE:
        samples = _resample_linear(samples, rate, TARGET_SAMPLE_RATE)
    return np.rint(samples).clip(-32768, 32767).astype(np.int16)


def _decode_mp3(data: bytes) -> np.ndarray | None:
    try:
        decoded = miniaudio.decode(
            data,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=TARGET_SAMPLE_RATE,
        )
    except miniaudio.DecodeError:
        return None
    return np.frombuffer(decoded.samples, dtype=np.int16)


def _resample_linear(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    dst_len = int(round(samples.size / src_rate * dst_rate))
    if dst_len <= 0:
        return np.empty(0, dtype=np.float64)
    src_t = np.arange(samples.size, dtype=np.float64) / src_rate
    dst_t = np.arange(dst_len, dtype=np.float64) / dst_rate
    return np.interp(dst_t, src_t, samples)


def _encode_wav(pcm: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_SAMPLE_RATE)
        wf.writeframes(pcm.astype("<i2").tobytes())
    return buf.getvalue()
