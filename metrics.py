"""Pipeline instrumentation for realtime voice sessions.

Tracks latency timestamps, connection events, dropped frames, VAD errors
and provider call counts. Uses ``summarize_latency`` from voice_pipeline.py
for p50/p95 computation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from voice_pipeline import summarize_latency


@dataclass
class SessionMetrics:
    """Metrics collected during a single realtime interview session."""

    # Timestamps (monotonic, seconds)
    session_start: float = 0.0
    speech_end: float = 0.0
    provider_processing: float = 0.0
    final_transcript: float = 0.0
    response_gen_start: float = 0.0
    first_tts_audio: float = 0.0
    playback_start: float = 0.0

    # Counters
    connection_successes: int = 0
    connection_failures: int = 0
    dropped_frames: int = 0
    vad_errors: int = 0
    provider_stt_calls: int = 0
    provider_tts_calls: int = 0
    frames_sent: int = 0
    transcripts_received: int = 0

    # Latency sample lists (milliseconds)
    stt_latencies_ms: list[float] = field(default_factory=list)
    tts_latencies_ms: list[float] = field(default_factory=list)
    e2e_latencies_ms: list[float] = field(default_factory=list)

    # -- recording helpers ---------------------------------------------------

    def mark_session_start(self) -> None:
        self.session_start = time.monotonic()

    def mark_speech_end(self) -> None:
        self.speech_end = time.monotonic()

    def mark_provider_processing(self) -> None:
        self.provider_processing = time.monotonic()

    def mark_final_transcript(self) -> None:
        self.final_transcript = time.monotonic()
        if self.speech_end > 0:
            self.stt_latencies_ms.append(
                (self.final_transcript - self.speech_end) * 1000
            )

    def mark_response_gen_start(self) -> None:
        self.response_gen_start = time.monotonic()

    def mark_first_tts_audio(self) -> None:
        self.first_tts_audio = time.monotonic()
        if self.response_gen_start > 0:
            self.tts_latencies_ms.append(
                (self.first_tts_audio - self.response_gen_start) * 1000
            )

    def mark_playback_start(self) -> None:
        self.playback_start = time.monotonic()
        if self.speech_end > 0:
            self.e2e_latencies_ms.append(
                (self.playback_start - self.speech_end) * 1000
            )

    def record_connection_success(self) -> None:
        self.connection_successes += 1

    def record_connection_failure(self) -> None:
        self.connection_failures += 1

    def record_dropped_frame(self) -> None:
        self.dropped_frames += 1

    def record_vad_error(self) -> None:
        self.vad_errors += 1

    def record_stt_call(self) -> None:
        self.provider_stt_calls += 1

    def record_tts_call(self) -> None:
        self.provider_tts_calls += 1

    def record_frame_sent(self) -> None:
        self.frames_sent += 1

    def record_transcript_received(self) -> None:
        self.transcripts_received += 1

    # -- summarisation -------------------------------------------------------

    def summary(self) -> dict:
        """Return a JSON-safe summary of collected metrics."""
        elapsed = (
            time.monotonic() - self.session_start if self.session_start > 0 else 0.0
        )
        result: dict = {
            "session_duration_s": round(elapsed, 2),
            "connection_successes": self.connection_successes,
            "connection_failures": self.connection_failures,
            "dropped_frames": self.dropped_frames,
            "vad_errors": self.vad_errors,
            "provider_stt_calls": self.provider_stt_calls,
            "provider_tts_calls": self.provider_tts_calls,
            "frames_sent": self.frames_sent,
            "transcripts_received": self.transcripts_received,
        }
        if self.stt_latencies_ms:
            result["stt_latency"] = summarize_latency(self.stt_latencies_ms)
        if self.tts_latencies_ms:
            result["tts_latency"] = summarize_latency(self.tts_latencies_ms)
        if self.e2e_latencies_ms:
            result["e2e_latency"] = summarize_latency(self.e2e_latencies_ms)
        return result
