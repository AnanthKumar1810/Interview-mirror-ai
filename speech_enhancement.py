"""Optional, auditable denoising for uploaded mono PCM16 speech.

This is a *baseline spectral-gating enhancer*, not a state-of-the-art neural
noise canceller.  It does not claim to improve ASR without measured WER data.
Original audio is never overwritten or persisted. We accept 8/16 kHz input and
produce 16 kHz PCM16 for the current Prisma contract.

Enhancement is opt-in: ``mode='spectral'``. In production benchmark raw and
processed audio with the same reference transcripts before setting a default.
"""
from __future__ import annotations

import io
import wave
from functools import lru_cache
from math import gcd

import numpy as np
from scipy.signal import resample_poly, stft, istft

from audio_tools import inspect_pcm16_wav

MAX_PEAK = 32767


@lru_cache(maxsize=1)
def _deepfilter_model():
    """Optional pretrained neural denoiser, loaded on first explicit request.

    Requires separately installed torch + deepfilternet and may download
    model weights; this build has NOT benchmarked its telephony WER.
    """
    try:
        from df.enhance import init_df, enhance
        import torch
    except ImportError as exc:
        raise ValueError("DeepFilterNet3 is not installed; use 'spectral' or install optional neural dependencies.") from exc
    model, state, *_ = init_df(model_base_dir="DeepFilterNet3", log_file=None)
    return model, state, enhance, torch


def _neural_denoise(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    model, state, enhance, torch = _deepfilter_model()
    model_rate = int(state.sr())
    factor = gcd(model_rate, sample_rate)
    upsampled = resample_poly(samples, model_rate // factor, sample_rate // factor)
    torch_wave = torch.from_numpy(np.asarray(upsampled, dtype=np.float32)[None, :])
    output = enhance(model, state, torch_wave).detach().cpu().numpy().reshape(-1)
    factor = gcd(sample_rate, model_rate)
    restored = resample_poly(output, sample_rate // factor, model_rate // factor)
    return restored[:len(samples)]



def _decode(raw: bytes) -> tuple[np.ndarray, int]:
    meta = inspect_pcm16_wav(raw)
    with wave.open(io.BytesIO(raw), "rb") as reader:
        samples = np.frombuffer(reader.readframes(reader.getnframes()), dtype="<i2").astype(np.float64)
    return samples / 32768.0, int(meta["sample_rate_hz"])


def _encode(samples: np.ndarray, rate: int = 16000) -> bytes:
    samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
    pcm = (np.clip(samples, -1.0, MAX_PEAK / 32768.0) * 32768).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm.tobytes())
    return output.getvalue()


def enhance_pcm16_wav(raw: bytes, *, mode: str = "off") -> tuple[bytes, dict]:
    """Return provider-compatible WAV and non-content diagnostic metadata.

    The noise profile uses a lower temporal quantile, then conservative
    minimum-gain masking and frequency smoothing to avoid zeroing phonemes.
    Speech distortion is possible; enhancement is disabled by default.
    """
    if mode not in ("off", "spectral", "deepfilter3"):
        raise ValueError("enhancement must be off, spectral, or deepfilter3")
    samples, sample_rate = _decode(raw)
    source_rate = sample_rate
    if sample_rate == 8000:
        samples = resample_poly(samples, 2, 1)
        sample_rate = 16000
    elif sample_rate != 16000:
        raise ValueError("Only 8 kHz or 16 kHz WAV is supported")
    if mode == "deepfilter3":
        samples = _neural_denoise(samples, sample_rate)
    elif mode == "spectral":
        # 32-ms Hann windows, 8-ms hops; stationary-noise gate only.
        _, _, transformed = stft(samples, fs=sample_rate, nperseg=512, noverlap=384,
                                 boundary="zeros", padded=True)
        magnitude = np.abs(transformed)
        noise_floor = np.quantile(magnitude, 0.15, axis=1, keepdims=True)
        gain = 1.0 - 0.85 * noise_floor / np.maximum(magnitude, 1e-9)
        gain = np.clip(gain, 0.22, 1.0)
        # Smooth the mask across frequency bins to reduce musical artifacts.
        gain = (np.roll(gain, 1, axis=0) + 2 * gain + np.roll(gain, -1, axis=0)) / 4.0
        _, restored = istft(transformed * gain, fs=sample_rate, nperseg=512, noverlap=384,
                            input_onesided=True, boundary=True)
        samples = restored[:len(samples)]
    output = _encode(samples)
    return output, {
        "enhancement": mode,
        "original_sample_rate_hz": source_rate,
        "provider_sample_rate_hz": sample_rate,
        "duration_seconds": round(len(samples) / sample_rate, 3),
        "output_size_bytes": len(output),
        "enhancement_accuracy_verified": False,
        "warning": "Enhancement may distort speech; compare ASR word error rate before using by default."
                   if mode != "off" else None,
    }
