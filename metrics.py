"""Pipeline instrumentation and telemetry for realtime voice sessions.

Tracks latency timestamps, connection events, dropped frames, VAD errors,
and provider call counts. Disentangles server monotonic clocks from browser
timing events. Computes nearest-rank p50 and p95 for:
  - end_of_speech_to_transcript
  - transcript_to_first_audio
  - end_of_speech_to_playback (audible in browser)
  - endpointing_delay
  - evaluation_stage
  - barge_in_audible_stop
Uses ``summarize_latency`` from voice_pipeline.py for percentile computations.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from voice_pipeline import summarize_latency


@dataclass
class SessionMetrics:
    """Metrics and telemetry collected during a single realtime interview session."""

    # Server Monotonic Timestamps (seconds)
    session_start: float = 0.0
    speech_end: float = 0.0
    endpointing_decision: float = 0.0
    provider_processing: float = 0.0
    final_transcript: float = 0.0
    response_gen_start: float = 0.0
    eval_completed: float = 0.0
    tts_dispatched: float = 0.0
    first_tts_audio: float = 0.0
    playback_start: float = 0.0  # server dispatch of first chunk
    barge_in_triggered: float = 0.0

    # Browser-Reported Timing Events (milliseconds from epoch or monotonic delta)
    browser_playback_start: float = 0.0
    browser_playback_stop: float = 0.0
    barge_in_audible_stop: float = 0.0

    # Core counters
    connection_successes: int = 0
    connection_failures: int = 0
    dropped_frames: int = 0
    vad_errors: int = 0
    provider_stt_calls: int = 0
    provider_tts_calls: int = 0
    frames_sent: int = 0
    transcripts_received: int = 0

    # Extended telemetry counters
    connection_attempts: int = 0
    first_attempt_failures: int = 0
    retry_recoveries: int = 0
    vad_segmentation_errors: int = 0
    premature_cutoffs: int = 0
    barge_ins: int = 0
    reprompts: int = 0

    # Latency sample lists (milliseconds)
    stt_latencies_ms: list[float] = field(default_factory=list)
    tts_latencies_ms: list[float] = field(default_factory=list)
    e2e_latencies_ms: list[float] = field(default_factory=list)

    eos_to_transcript_samples: list[float] = field(default_factory=list)
    transcript_to_first_audio_samples: list[float] = field(default_factory=list)
    eos_to_playback_samples: list[float] = field(default_factory=list)
    endpointing_delay_samples: list[float] = field(default_factory=list)
    stt_duration_samples: list[float] = field(default_factory=list)
    tts_duration_samples: list[float] = field(default_factory=list)
    eval_duration_samples: list[float] = field(default_factory=list)
    barge_in_stop_samples: list[float] = field(default_factory=list)

    # -- Property aliases for backwards and naming compatibility ------------

    @property
    def session_start_ts(self) -> float:
        return self.session_start

    @session_start_ts.setter
    def session_start_ts(self, val: float) -> None:
        self.session_start = val

    @property
    def speech_end_ts(self) -> float:
        return self.speech_end

    @speech_end_ts.setter
    def speech_end_ts(self, val: float) -> None:
        self.speech_end = val

    @property
    def final_transcript_ts(self) -> float:
        return self.final_transcript

    @final_transcript_ts.setter
    def final_transcript_ts(self, val: float) -> None:
        self.final_transcript = val

    @property
    def evaluation_done_ts(self) -> float:
        return self.eval_completed or self.response_gen_start

    @evaluation_done_ts.setter
    def evaluation_done_ts(self, val: float) -> None:
        self.eval_completed = val
        self.response_gen_start = val

    @property
    def first_tts_audio_ts(self) -> float:
        return self.first_tts_audio

    @first_tts_audio_ts.setter
    def first_tts_audio_ts(self, val: float) -> None:
        self.first_tts_audio = val

    @property
    def playback_start_ts(self) -> float:
        return self.playback_start

    @playback_start_ts.setter
    def playback_start_ts(self, val: float) -> None:
        self.playback_start = val

    @property
    def stt_calls(self) -> int:
        return self.provider_stt_calls

    @stt_calls.setter
    def stt_calls(self, val: int) -> None:
        self.provider_stt_calls = val

    @property
    def tts_calls(self) -> int:
        return self.provider_tts_calls

    @tts_calls.setter
    def tts_calls(self, val: int) -> None:
        self.provider_tts_calls = val

    # -- Recording helpers ---------------------------------------------------

    def mark_session_start(self, ts: float | None = None) -> None:
        self.session_start = ts or time.monotonic()
        self.connection_attempts += 1

    def mark_speech_end(self, ts: float | None = None) -> None:
        self.speech_end = ts or time.monotonic()

    def mark_endpointing_decision(self, ts: float | None = None) -> None:
        now = ts or time.monotonic()
        self.endpointing_decision = now
        if self.speech_end > 0:
            diff = (now - self.speech_end) * 1000
            if diff >= 0:
                self.endpointing_delay_samples.append(round(diff, 2))

    def mark_provider_processing(self, ts: float | None = None) -> None:
        self.provider_processing = ts or time.monotonic()

    def mark_final_transcript(self, ts: float | None = None) -> None:
        now = ts or time.monotonic()
        self.final_transcript = now
        if self.speech_end > 0:
            diff = (now - self.speech_end) * 1000
            if diff >= 0:
                self.stt_latencies_ms.append(diff)
                self.eos_to_transcript_samples.append(round(diff, 2))
                self.stt_duration_samples.append(round(diff, 2))

    def mark_response_gen_start(self, ts: float | None = None) -> None:
        self.response_gen_start = ts or time.monotonic()

    def mark_evaluation_done(self, ts: float | None = None) -> None:
        now = ts or time.monotonic()
        self.eval_completed = now
        self.response_gen_start = self.response_gen_start or now
        if self.final_transcript > 0:
            diff = round((now - self.final_transcript) * 1000, 2)
            if diff >= 0:
                self.eval_duration_samples.append(diff)

    def mark_tts_dispatched(self, ts: float | None = None) -> None:
        self.tts_dispatched = ts or time.monotonic()

    def mark_first_tts_audio(self, ts: float | None = None) -> None:
        now = ts or time.monotonic()
        self.first_tts_audio = now
        ref_start = self.tts_dispatched or self.response_gen_start
        if ref_start > 0:
            diff = (now - ref_start) * 1000
            if diff >= 0:
                self.tts_latencies_ms.append(diff)
                self.tts_duration_samples.append(round(diff, 2))
        if self.final_transcript > 0:
            diff = round((now - self.final_transcript) * 1000, 2)
            if diff >= 0:
                self.transcript_to_first_audio_samples.append(diff)

    def mark_playback_start(self, ts: float | None = None) -> None:
        now = ts or time.monotonic()
        self.playback_start = now
        if self.speech_end > 0:
            diff = (now - self.speech_end) * 1000
            if diff >= 0:
                self.e2e_latencies_ms.append(diff)
                self.eos_to_playback_samples.append(round(diff, 2))

    def record_browser_playback_start(self, client_ms: int = 0) -> None:
        self.browser_playback_start = time.monotonic()

    def record_browser_playback_stop(self, client_ms: int = 0) -> None:
        self.browser_playback_stop = time.monotonic()

    def record_barge_in_stop(self, delay_ms: float = 0.0) -> None:
        if delay_ms > 0:
            self.barge_in_stop_samples.append(round(delay_ms, 2))

    def record_connection_success(self) -> None:
        self.connection_successes += 1

    def record_connection_failure(self, is_retry: bool = False) -> None:
        self.connection_failures += 1
        if not is_retry:
            self.first_attempt_failures += 1

    def record_retry_recovery(self) -> None:
        self.retry_recoveries += 1

    def record_dropped_frame(self) -> None:
        self.dropped_frames += 1

    def record_vad_error(self) -> None:
        self.vad_errors += 1
        self.vad_segmentation_errors += 1

    def record_premature_cutoff(self) -> None:
        self.premature_cutoffs += 1

    def record_barge_in(self) -> None:
        self.barge_ins += 1
        self.barge_in_triggered = time.monotonic()

    def record_reprompt(self) -> None:
        self.reprompts += 1

    def record_stt_call(self) -> None:
        self.provider_stt_calls += 1

    def record_tts_call(self) -> None:
        self.provider_tts_calls += 1

    def record_frame_sent(self) -> None:
        self.frames_sent += 1

    def record_transcript_received(self) -> None:
        self.transcripts_received += 1

    # -- Summarisation -------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a JSON-safe summary of collected telemetry and percentiles."""
        elapsed = (
            time.monotonic() - self.session_start if self.session_start > 0 else 0.0
        )
        result: dict[str, Any] = {
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

        # Extended counters & breakdowns
        result["counters"] = {
            "connection_attempts": self.connection_attempts,
            "connection_successes": self.connection_successes,
            "connection_failures": self.connection_failures,
            "first_attempt_failures": self.first_attempt_failures,
            "retry_recoveries": self.retry_recoveries,
            "dropped_frames": self.dropped_frames,
            "vad_segmentation_errors": self.vad_segmentation_errors,
            "premature_cutoffs": self.premature_cutoffs,
            "barge_ins": self.barge_ins,
            "reprompts": self.reprompts,
            "frames_sent": self.frames_sent,
            "stt_calls": self.provider_stt_calls,
            "tts_calls": self.provider_tts_calls,
            "transcripts_received": self.transcripts_received,
        }

        def safe_summary(samples: list[float]) -> dict[str, Any]:
            if not samples:
                return {"p50_ms": None, "p95_ms": None, "max_ms": None, "samples": 0}
            try:
                return summarize_latency(samples)
            except ValueError:
                return {"p50_ms": None, "p95_ms": None, "max_ms": None, "samples": len(samples)}

        result["latencies"] = {
            "end_of_speech_to_transcript": safe_summary(self.eos_to_transcript_samples or self.stt_latencies_ms),
            "transcript_to_first_audio": safe_summary(self.transcript_to_first_audio_samples),
            "end_of_speech_to_playback": safe_summary(self.eos_to_playback_samples or self.e2e_latencies_ms),
            "endpointing_delay": safe_summary(self.endpointing_delay_samples),
            "stt_stage": safe_summary(self.stt_duration_samples or self.stt_latencies_ms),
            "evaluation_stage": safe_summary(self.eval_duration_samples),
            "tts_stage": safe_summary(self.tts_duration_samples or self.tts_latencies_ms),
            "barge_in_stop": safe_summary(self.barge_in_stop_samples),
        }
        result["timing_definitions"] = {
            "end_of_speech_to_transcript": "From candidate speech cessation to Prisma final transcript arrival.",
            "transcript_to_first_audio": "From final transcript arrival through scoring to first Timbre audio chunk.",
            "end_of_speech_to_playback": "Total turnaround: candidate speech cessation to audio playback dispatch.",
            "endpointing_delay": "Conversational pause aggregation window (1.8s baseline) before declaring speech complete.",
        }
        result["note"] = "Latency includes conversational silence pause window (1.2–1.8s) required for turn detection."
        return result
