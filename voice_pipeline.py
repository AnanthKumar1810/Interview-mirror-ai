"""Measurable async voice pipeline independent of web frameworks and paid APIs.

This is a batch-turn teaching harness, NOT a streaming LiveKit voice agent.
It demonstrates cooperative async I/O, dependent-stage execution, timing,
provider timeouts, error surfaces, and injectable scoring. No audio or
transcripts are written to logs or disk.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from math import ceil
from time import perf_counter
from typing import Any, Awaitable, Callable, Protocol


class VoiceProvider(Protocol):
    async def transcribe(self, audio_wav: bytes, language: str) -> dict: ...
    async def synthesize(self, text: str, language: str) -> bytes: ...


class VoiceStageError(RuntimeError):
    def __init__(self, stage: str, kind: str):
        self.stage = stage
        self.kind = kind
        super().__init__(f"{stage} stage failed ({kind}).")


@dataclass(frozen=True)
class VoiceTurnResult:
    transcript: str
    score: dict[str, Any]
    audio: bytes
    timings_ms: dict[str, float]

    def safe_summary(self) -> dict[str, Any]:
        """Privacy-friendly telemetry: stages and sizes, not content or recordings."""
        return {
            "timings_ms": self.timings_ms,
            "audio_bytes": len(self.audio),
            "transcript_characters": len(self.transcript),
        }


class AsyncVoicePipeline:
    """STT -> scoring -> TTS; stage dependencies require sequential awaits.

    ``scorer`` is the existing synchronous InterviewMirror scoring function,
    adapted with ``asyncio.to_thread`` to avoid blocking the event loop.
    Keep it free of shared mutable state: a timed-out worker thread is NOT
    forcibly stopped by cancellation. Only the native async provider stages
    are subject to ``asyncio.wait_for`` hard coroutine timeouts.
    """

    def __init__(
        self,
        provider: VoiceProvider,
        scorer: Callable[[str], dict[str, Any]],
        *,
        stt_timeout_s: float = 30.0,
        tts_timeout_s: float = 30.0,
    ):
        if stt_timeout_s <= 0 or tts_timeout_s <= 0:
            raise ValueError("Timeouts must be positive")
        self.provider = provider
        self.scorer = scorer
        self.stt_timeout_s = stt_timeout_s
        self.tts_timeout_s = tts_timeout_s

    async def run(self, audio_wav: bytes, *, language: str, reply_text: str) -> VoiceTurnResult:
        if not audio_wav or not reply_text.strip():
            raise ValueError("Audio and reply text are required")
        t0 = perf_counter()
        marks: dict[str, float] = {}

        async def timed_provider(stage: str, call: Awaitable, timeout: float):
            started = perf_counter()
            try:
                return await asyncio.wait_for(call, timeout=timeout)
            except TimeoutError as exc:
                raise VoiceStageError(stage, "timeout") from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Don't echo possibly sensitive provider errors to callers.
                raise VoiceStageError(stage, "provider_error") from exc
            finally:
                marks[stage] = round((perf_counter() - started) * 1000, 2)

        transcription = await timed_provider(
            "stt", self.provider.transcribe(audio_wav, language), self.stt_timeout_s
        )
        transcript = transcription.get("transcript") if isinstance(transcription, dict) else None
        if not isinstance(transcript, str) or not transcript.strip():
            raise VoiceStageError("stt", "invalid_transcript")

        start_score = perf_counter()
        try:
            score = await asyncio.to_thread(self.scorer, transcript.strip())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise VoiceStageError("scoring", "scorer_error") from exc
        finally:
            marks["scoring"] = round((perf_counter() - start_score) * 1000, 2)
        if not isinstance(score, dict):
            raise VoiceStageError("scoring", "invalid_score")

        audio = await timed_provider(
            "tts", self.provider.synthesize(reply_text, language), self.tts_timeout_s
        )
        if not isinstance(audio, bytes) or not audio:
            raise VoiceStageError("tts", "empty_audio")

        marks["total"] = round((perf_counter() - t0) * 1000, 2)
        return VoiceTurnResult(transcript.strip(), score, audio, marks)


def summarize_latency(samples_ms: list[float]) -> dict[str, float]:
    """Nearest-rank p50/p95 for a nonempty list of completed calls."""
    if not samples_ms or any(not isinstance(x, (float, int)) or x < 0 for x in samples_ms):
        raise ValueError("Expected nonnegative latency samples")
    s = sorted(samples_ms)
    return {
        "p50_ms": round(s[ceil(0.50 * len(s)) - 1], 2),
        "p95_ms": round(s[ceil(0.95 * len(s)) - 1], 2),
        "max_ms": round(s[-1], 2),
        "samples": len(s),
    }
