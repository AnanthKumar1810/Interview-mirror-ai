"""Small, deterministic WAV preflight shared by demo checks and live Prisma uploads.

This never contacts Gnani or stores recordings. Statistics are diagnostic, not a
speech-recognition or clinical-quality audio assessment.
"""
from __future__ import annotations

from array import array
import io
import math
import sys
import wave

MAX_AUDIO_BYTES = 4_000_000
ALLOWED_AUDIO_MIME = {"audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"}


def inspect_pcm16_wav(raw: bytes) -> dict:
    if not raw or len(raw) > MAX_AUDIO_BYTES:
        raise ValueError("Audio is empty or too large (maximum 4 MB).")
    try:
        with wave.open(io.BytesIO(raw), "rb") as audio:
            rate = audio.getframerate()
            nchannels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            num_frames = audio.getnframes()
            compression = audio.getcomptype()
            duration = num_frames / rate if rate else 0
            if (nchannels != 1 or sample_width != 2 or rate not in (8000, 16000)
                    or compression != "NONE" or not (0.2 <= duration <= 30)):
                raise ValueError("Audio must be PCM WAV: mono, 16-bit, 8/16 kHz, 0.2–30 seconds.")
            samples = array("h")
            samples.frombytes(audio.readframes(num_frames))
    except (wave.Error, EOFError, ValueError, ZeroDivisionError) as exc:
        raise ValueError("Audio must be PCM WAV: mono, 16-bit, 8/16 kHz, 0.2–30 seconds.") from exc
    if len(samples) != num_frames:
        raise ValueError("Audio recording is incomplete or corrupted.")
    if not samples:
        raise ValueError("Audio recording is empty.")
    if sys.byteorder != "little":
        samples.byteswap()
    stride = max(1, len(samples) // 25000)
    taken = samples[::stride]
    peak = max(abs(n) for n in taken) / 32768
    rms = math.sqrt(sum(n * n for n in taken) / len(taken)) / 32768
    dbfs = round(20 * math.log10(rms), 1) if rms else None
    quiet = rms < 0.0005  # Strongly conservative threshold (~ -66 dBFS).
    return {
        "format_valid": True,
        "duration_seconds": round(duration, 2),
        "sample_rate_hz": rate,
        "channels": nchannels,
        "sample_width_bits": sample_width * 8,
        "size_bytes": len(raw),
        "rms_dbfs": dbfs,
        "peak_fraction": round(peak, 4),
        "possibly_silent": quiet,
        "message": ("Recording appears very quiet. Check microphone permissions or input level."
                    if quiet else "WAV format passed; play it back to confirm the speech is intelligible."),
    }
