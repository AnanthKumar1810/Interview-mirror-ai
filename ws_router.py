"""FastAPI WebSocket router for hands-free realtime voice interview.

Endpoint: ``/ws/interview``

Manages:
  - Authoritative persistent session in SQLiteStore with authentication/ownership
  - Decoupled, independently supervised concurrent async tasks:
      1. ``_browser_audio_ingest`` (reads binary frames + JSON control + client telemetry)
      2. ``_gnani_stt_events`` (forwards audio to Prisma, aggregates segments, configurable endpointing)
      3. ``_outgoing_browser_messages`` (pushes prioritized messages to client)
      4. ``_dispatch_tts`` (supervised TTS synthesis with generation ID tracking)
  - Configurable candidate pause aggregation:
      - Fixed: 1.8s
      - Two-Stage: Prisma VAD + 0.6s grace period
      - Adaptive: checks speech syntax and connector words
  - Autonomous turn progression: Speaks question → Listens → Detects pause → Evaluates → Speaks next
  - Gentle reprompt after 15s candidate hesitation
  - Barge-in cancellation without undocumented provider calls
  - Acoustic echo protection while interviewer is speaking
  - Graceful "End interview" handling and report persistence
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import os
import struct
import time
import uuid
import wave
from dataclasses import asdict
from typing import Optional, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from urllib.parse import urlparse

from ws_protocol import (
    PROTOCOL_VERSION,
    MAX_QUEUE_DEPTH,
    MAX_SESSION_DURATION_S,
    PCM_FRAME_BYTES,
    SessionStart,
    SessionResume,
    SessionAck,
    ProviderEvent,
    ErrorMessage,
    TranscriptMessage,
    TurnStateMessage,
    IntentMessage,
    BargeInMessage,
    RepromptMessage,
    TTSAudioMeta,
    TTSAudioComplete,
    MetricsMessage,
    PingMessage,
    PongMessage,
    parse_message,
    is_pcm_frame,
    _next_seq,
)
from interview_state import InterviewState, InterviewStateMachine, InvalidTransition
from conversational_engine import (
    INTENT_CLARIFICATION,
    INTENT_REPEAT,
    INTENT_UNCERTAINTY,
    INTENT_SKIP,
    INTENT_ANSWER,
)
from gnani_streaming import PrismaStreamingClient, TimbreStreamingClient
from gnani import GnaniClient, VOICE
from metrics import SessionMetrics

logger = logging.getLogger(__name__)

ws_router = APIRouter()

# Conversational timing configuration
ANSWER_PAUSE_TIMEOUT_S = 1.8  # Default pause duration to confirm candidate completed answer
NO_SPEECH_REPROMPT_S = 15.0   # Silence timeout before gentle spoken reprompt

REPROMPTS = {
    "en-IN": "Take your time. Whenever you're ready, please share your thoughts on the question.",
    "te-IN": "మీ సమయం తీసుకోండి. మీరు సిద్ధంగా ఉన్నప్పుడు మీ ఆలోచనలను పంచుకోండి.",
    "hi-IN": "अपना समय लें। जब भी आप तैयार हों, कृपया अपने विचार साझा करें.",
}


class _SessionContext:
    """Session state shared across concurrent tasks with SQLite backing."""

    def __init__(
        self,
        session_id: str,
        track: str,
        language: str,
        stt_model: str,
        consent: bool,
        store: Any = None,
        owner_id: str | None = None,
        endpointing_policy: str = "fixed",
        initial_seed: Optional[dict] = None,
        max_questions: int = 3,
        role: str = "Software Engineer",
    ) -> None:
        self.session_id = session_id
        self.track = track
        self.language = language
        self.stt_model = stt_model
        self.store = store
        self.owner_id = owner_id
        self.endpointing_policy = endpointing_policy
        self.session_version = 0

        self.state_machine = InterviewStateMachine(
            track=track,
            language=language,
            max_questions=max_questions,
            role=role,
            initial_question_spec=initial_seed,
        )
        self.state_machine.consent_given = consent
        self.metrics = SessionMetrics()

        self.trace_id: str = str(uuid.uuid4())
        self.seq: int = 0
        self.generation_id: int = 0  # incremented on barge-in to invalidate stale audio

        # Turn audio & segment aggregation
        self.accumulated_segments: list[str] = []
        self.reprompt_given: bool = False
        self.speech_active: bool = False
        self.last_speech_time: float = 0.0
        self.last_audio_frame_time: float = 0.0

        # Concurrent queues
        self.audio_to_stt: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=MAX_QUEUE_DEPTH)
        self.outgoing: asyncio.Queue[str | bytes] = asyncio.Queue(maxsize=MAX_QUEUE_DEPTH)
        self.control_outgoing: asyncio.Queue[str] = asyncio.Queue(maxsize=128)

        # Control flags and synchronization
        self.active = True
        self.active_tts_task: Optional[asyncio.Task] = None
        self.finalizing_lock = asyncio.Lock()
        self.barge_in_event = asyncio.Event()
        self.client_playback_active = False

    def next_seq(self) -> int:
        self.seq = _next_seq(self.seq)
        return self.seq

    def new_generation(self) -> int:
        self.generation_id += 1
        return self.generation_id

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Append an event to SQLiteStore session_events if available."""
        if self.store and hasattr(self.store, "log_event"):
            try:
                self.store.log_event(self.session_id, event_type, payload, trace_id=self.trace_id)
            except Exception as e:
                logger.warning("Could not log event %s: %s", event_type, e)


def _calculate_pause_timeout(ctx: _SessionContext) -> float:
    """Calculate pause window based on configured endpointing policy."""
    policy = ctx.endpointing_policy
    if policy == "two_stage":
        return 0.6  # Short application grace period after provider segment
    elif policy == "adaptive":
        text = " ".join(ctx.accumulated_segments).strip().lower()
        words = text.split()
        if not words:
            return 1.8
        trailing_connectors = {"and", "because", "so", "but", "like", "when", "if", "or", "కాబట్టి", "ఎందుకంటే", "क्योंकि"}
        if words[-1] in trailing_connectors:
            return 2.2  # Grant extra time if candidate paused mid-sentence
        if len(words) > 18 and text[-1] in (".", "!", "?", "।"):
            return 1.2  # Earlier cutoff for long declarative sentence with punctuation
        return 1.5
    return ANSWER_PAUSE_TIMEOUT_S


async def _enqueue_or_drop(
    queue: asyncio.Queue,
    item: Any,
    ctx: _SessionContext,
    label: str = "outgoing",
) -> None:
    """Put item on queue; drop oldest frame if full to prevent unbounded lag."""
    if queue.full():
        try:
            queue.get_nowait()
            ctx.metrics.record_dropped_frame()
            logger.debug("Backpressure: dropped oldest %s frame", label)
        except asyncio.QueueEmpty:
            pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        ctx.metrics.record_dropped_frame()


async def _send_json(ctx: _SessionContext, msg_dict: dict) -> None:
    """Enqueue JSON control frame for client delivery with priority."""
    msg_dict["sequence_number"] = ctx.next_seq()
    msg_dict["protocol_version"] = PROTOCOL_VERSION
    msg_dict["timestamp_ms"] = int(time.time() * 1000)
    json_str = json.dumps(msg_dict, ensure_ascii=False)
    try:
        ctx.control_outgoing.put_nowait(json_str)
    except asyncio.QueueFull:
        await _enqueue_or_drop(ctx.outgoing, json_str, ctx, "control")


async def _send_binary(ctx: _SessionContext, data: bytes) -> None:
    """Enqueue binary audio frame for client delivery."""
    await _enqueue_or_drop(ctx.outgoing, data, ctx, "audio-out")


async def _send_tts_complete(ctx: _SessionContext, generation_id: int) -> None:
    """Queue completion behind every binary chunk of this audio generation."""
    msg = TTSAudioComplete(generation_id=generation_id).__dict__
    msg["sequence_number"] = ctx.next_seq()
    msg["protocol_version"] = PROTOCOL_VERSION
    msg["timestamp_ms"] = int(time.time() * 1000)
    await _enqueue_or_drop(ctx.outgoing, json.dumps(msg), ctx, "tts-complete")


def _friendly_state_name(state: InterviewState) -> str:
    """Map internal state enum to user-facing readable status."""
    mapping = {
        InterviewState.waiting: "Connecting…",
        InterviewState.asking: "Interviewer speaking",
        InterviewState.listening: "Listening to your answer",
        InterviewState.transcribing: "Processing answer",
        InterviewState.review: "Reviewing transcript",
        InterviewState.feedback: "Evaluating feedback",
        InterviewState.followup: "Preparing next question",
        InterviewState.completed: "Complete",
    }
    return mapping.get(state, state.value)


async def _emit_turn_state(ctx: _SessionContext, feedback: Optional[dict] = None) -> None:
    """Emit turn state control envelope to client."""
    sm = ctx.state_machine
    msg = TurnStateMessage(
        state=_friendly_state_name(sm.current_state),
        raw_state=sm.current_state.value,
        question=sm.current_question_text() or "",
        question_number=sm.question_index + 1 if sm.question_index >= 0 else 1,
        feedback=feedback,
        session_id=ctx.session_id,
    )
    await _send_json(ctx, msg.__dict__)


def _persist_to_store(ctx: _SessionContext) -> None:
    """Synchronize current session state into SQLiteStore."""
    if not ctx.store:
        return
    sm = ctx.state_machine
    answers_payload = [
        {
            "turn_id": a.get("turn_id"),
            "question": a.get("question"),
            "question_kind": a.get("question_kind"),
            "question_reason": a.get("question_reason"),
            "provider_transcript": a.get("provider_transcript"),
            "edited_transcript": a.get("edited_transcript"),
            "transcript": a.get("transcript"),
            "feedback": a.get("feedback"),
            "score": a.get("feedback", {}).get("score", 0),
        }
        for a in sm.answers
    ]
    state_payload = {
        "session_id": ctx.session_id,
        "track": sm.track,
        "language": sm.language,
        "current_state": sm.current_state.value,
        "question_index": sm.question_index,
        "answers": answers_payload,
        "metrics": ctx.metrics.summary(),
        "is_complete": sm.is_complete,
        "owner_id": ctx.owner_id,
        "personalized_seed": sm.personalized_seed,
    }
    try:
        existing = ctx.store.get_session(ctx.session_id, ctx.owner_id)
        if existing:
            ctx.store.update_session(ctx.session_id, ctx.owner_id, state_payload, existing["version"])
        else:
            ctx.store.create_session(ctx.session_id, state_payload, ctx.owner_id, 86400)
    except Exception as exc:
        logger.warning("Could not persist session %s to SQLiteStore: %s", ctx.session_id, exc)


# ---------------------------------------------------------------------------
# Task 1: Ingest browser audio, JSON control & client telemetry
# ---------------------------------------------------------------------------

async def _browser_audio_ingest(ws: WebSocket, ctx: _SessionContext) -> None:
    """Read binary PCM frames and JSON control messages from the browser."""
    try:
        while ctx.active:
            raw = await ws.receive()
            if raw.get("type") == "websocket.disconnect":
                ctx.active = False
                return

            # Binary audio frame (512 samples / 1024 bytes PCM16 LE)
            if "bytes" in raw and raw["bytes"]:
                frame = raw["bytes"]
                if not is_pcm_frame(frame):
                    await _send_json(ctx, ErrorMessage(
                        code="invalid_audio_frame",
                        message="Expected one 1024-byte PCM frame.",
                        recoverable=True,
                    ).__dict__)
                    continue
                now = time.monotonic()
                ctx.last_audio_frame_time = now

                # Acoustic Echo Protection:
                # If coach is actively speaking (asking state), do not ingest mic audio
                # into Prisma STT unless candidate is actively barging in
                if ctx.state_machine.current_state == InterviewState.asking or ctx.client_playback_active:
                    continue

                if ctx.state_machine.current_state == InterviewState.listening:
                    await _enqueue_or_drop(ctx.audio_to_stt, frame, ctx, "audio-in")
                    ctx.metrics.record_frame_sent()
                continue

            # JSON control frame
            text = raw.get("text", "")
            if not text:
                continue

            try:
                msg = parse_message(text)
            except Exception:
                await _send_json(ctx, ErrorMessage(
                    code="parse_error", message="Invalid JSON format", recoverable=True
                ).__dict__)
                continue

            if msg.type == "ping":
                await _send_json(ctx, PongMessage(turn_id=msg.turn_id).__dict__)

            elif msg.type == "playback_start":
                ctx.client_playback_active = True
                client_ms = getattr(msg, "client_timestamp_ms", 0)
                ctx.metrics.record_browser_playback_start(client_ms)

            elif msg.type == "playback_stop":
                if getattr(msg, "generation_id", -1) == ctx.generation_id:
                    ctx.client_playback_active = False
                client_ms = getattr(msg, "client_timestamp_ms", 0)
                ctx.metrics.record_browser_playback_stop(client_ms)

            elif msg.type == "barge_in":
                # Candidate spoke over interviewer
                logger.info("Candidate barge-in detected on session %s", ctx.session_id)
                ctx.metrics.record_barge_in()
                stop_delay = getattr(msg, "stop_delay_ms", 0.0)
                if stop_delay > 0:
                    ctx.metrics.record_barge_in_stop(stop_delay)

                # Invalidate generation and cancel active TTS task
                ctx.new_generation()
                ctx.client_playback_active = False
                ctx.log_event("barge_in", {"generation_id": ctx.generation_id, "stop_delay_ms": stop_delay})
                if ctx.active_tts_task and not ctx.active_tts_task.done():
                    ctx.active_tts_task.cancel()

                if ctx.state_machine.current_state == InterviewState.asking:
                    ctx.state_machine.transition(InterviewState.listening)
                    await _emit_turn_state(ctx)

                await _send_json(ctx, BargeInMessage(generation_id=ctx.generation_id).__dict__)

            elif msg.type == "end_interview":
                # User pressed 'End interview'
                logger.info("Candidate ended interview early on session %s", ctx.session_id)
                ctx.log_event("session_ended_early", {"answered": ctx.state_machine.question_index})
                ctx.state_machine.end_interview()
                _persist_to_store(ctx)
                await _emit_turn_state(ctx)
                await _send_json(ctx, MetricsMessage(data=ctx.metrics.summary()).__dict__)
                await asyncio.sleep(0.05)
                ctx.active = False
                return

    except WebSocketDisconnect:
        ctx.active = False
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("browser_audio_ingest error: %s", exc)
        ctx.active = False


# ---------------------------------------------------------------------------
# Task 2: Prisma STT + Candidate Pause Aggregator
# ---------------------------------------------------------------------------

def _calculate_rms(chunk: bytes) -> float:
    """Calculate RMS energy of 16-bit PCM audio frame for energy-based VAD."""
    if len(chunk) < 2:
        return 0.0
    count = len(chunk) // 2
    samples = struct.unpack(f"<{count}h", chunk[:count * 2])
    sum_sq = sum(s * s for s in samples)
    return math.sqrt(sum_sq / count)


async def _fallback_vad_stt(ctx: _SessionContext) -> None:
    """Robust VAD-driven STT using Gnani Prisma v2.5 REST when WebSocket streaming is unavailable."""
    gc = GnaniClient()
    if not gc.enabled:
        await _send_json(ctx, ErrorMessage(
            code="stt_unavailable",
            message="Gnani speech recognition is unavailable. Check the server API key.",
            recoverable=False,
        ).__dict__)
        ctx.active = False
        return
    logger.info("Operating in VAD-driven STT mode for session %s (Prisma v2.5 REST)", ctx.session_id)
    ctx.metrics.record_connection_success()
    ctx.metrics.record_stt_call()

    await _send_json(ctx, ProviderEvent(
        event="connected",
        detail={"provider": "prisma-rest", "model": "prisma-v2.5"},
    ).__dict__)

    accumulated_pcm = bytearray()
    speech_active = False
    speech_frames = 0
    silence_frames = 0
    noise_floor = 100.0
    ENERGY_THRESHOLD = float(os.getenv("IM_VAD_ENERGY_THRESHOLD", "260.0"))

    pause_timer_task: Optional[asyncio.Task] = None
    reprompt_timer_task: Optional[asyncio.Task] = None

    async def _on_pause_expired():
        nonlocal accumulated_pcm, speech_active, pause_timer_task
        try:
            pause_s = _calculate_pause_timeout(ctx)
            await asyncio.sleep(pause_s)
            if not ctx.active or not accumulated_pcm:
                pause_timer_task = None
                return
            logger.info("Candidate pause confirmed (%d bytes). Transcribing via Prisma v2.5...", len(accumulated_pcm))
            ctx.speech_active = False
            speech_active = False
            pause_timer_task = None
            ctx.metrics.mark_speech_end(time.monotonic())

            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(bytes(accumulated_pcm))
            wav_bytes = buf.getvalue()
            accumulated_pcm.clear()

            transcript = ""
            if gc.enabled and len(wav_bytes) > 6400:  # ~0.2s of audio
                try:
                    result = await asyncio.to_thread(gc.transcribe, wav_bytes, ctx.state_machine.language)
                    transcript = result.get("transcript", "").strip()
                except Exception as stt_err:
                    logger.warning("Prisma REST transcription error: %s", stt_err)

            if not transcript:
                await _send_json(ctx, ErrorMessage(
                    code="transcription_failed",
                    message="Gnani did not return a transcript. Please try answering again.",
                    recoverable=True,
                ).__dict__)
                return

            ctx.accumulated_segments = [transcript]
            await _send_json(ctx, TranscriptMessage(
                text=transcript,
                is_final=True,
                source="gnani_prisma",
                segment_id=str(uuid.uuid4()),
            ).__dict__)

            await _finalize_turn(ctx)
        except asyncio.CancelledError:
            pass

    async def _on_reprompt_check():
        try:
            await asyncio.sleep(NO_SPEECH_REPROMPT_S)
            if (
                ctx.active
                and ctx.state_machine.current_state == InterviewState.listening
                and not ctx.accumulated_segments
                and not speech_active
                and not ctx.reprompt_given
            ):
                ctx.reprompt_given = True
                ctx.metrics.record_reprompt()
                reprompt_text = REPROMPTS.get(ctx.state_machine.language, REPROMPTS["en-IN"])
                await _send_json(ctx, RepromptMessage(text=reprompt_text).__dict__)
                ctx.state_machine.transition(InterviewState.asking)
                await _emit_turn_state(ctx)
                _dispatch_tts(ctx, reprompt_text)
        except asyncio.CancelledError:
            pass

    reprompt_timer_task = asyncio.create_task(_on_reprompt_check())

    try:
        while ctx.active:
            try:
                chunk = await asyncio.wait_for(ctx.audio_to_stt.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if chunk is None:
                break
            if len(chunk) < 2:
                continue

            rms = _calculate_rms(chunk)
            if not speech_active:
                noise_floor = 0.95 * noise_floor + 0.05 * min(rms, 400.0)
            threshold = max(ENERGY_THRESHOLD, min(500.0, noise_floor * 2.0))

            if rms > threshold:
                speech_frames += 1
                silence_frames = 0
                if speech_frames >= 2:
                    if not speech_active:
                        speech_active = True
                        ctx.speech_active = True
                        ctx.last_speech_time = time.monotonic()
                        if reprompt_timer_task and not reprompt_timer_task.done():
                            reprompt_timer_task.cancel()
                        if ctx.state_machine.current_state == InterviewState.asking:
                            ctx.state_machine.transition(InterviewState.listening)
                            await _emit_turn_state(ctx)
                        await _send_json(ctx, ProviderEvent(
                            event="speech_start",
                            detail={"provider": "prisma-rest", "energy": round(rms, 1)},
                        ).__dict__)

                    # Candidate is speaking; cancel any running pause timer
                    if pause_timer_task and not pause_timer_task.done():
                        pause_timer_task.cancel()
                        pause_timer_task = None

                if speech_active:
                    accumulated_pcm.extend(chunk)
            else:
                silence_frames += 1
                if speech_active:
                    accumulated_pcm.extend(chunk)
                    if silence_frames >= 5:  # ~160ms of silence after speech
                        speech_frames = 0
                        # ONLY create timer if one is not already actively ticking
                        if pause_timer_task is None or pause_timer_task.done():
                            pause_timer_task = asyncio.create_task(_on_pause_expired())
    finally:
        if pause_timer_task and not pause_timer_task.done():
            pause_timer_task.cancel()
        if reprompt_timer_task and not reprompt_timer_task.done():
            reprompt_timer_task.cancel()


async def _live_prisma_stt(ctx: _SessionContext) -> None:
    async with PrismaStreamingClient(
        language_code=ctx.state_machine.language,
        model=ctx.stt_model,
        silence_timeout_s=1.5,
    ) as prisma:
            ctx.metrics.record_connection_success()
            ctx.metrics.record_stt_call()

            await _send_json(ctx, ProviderEvent(
                event="connected",
                detail={"provider": "prisma", "model": ctx.stt_model, "endpoint": prisma.ws_url},
            ).__dict__)

            # Sub-task A: feed audio queue to Prisma
            async def _feed_audio() -> None:
                while ctx.active:
                    try:
                        chunk = await asyncio.wait_for(ctx.audio_to_stt.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    if chunk is None:
                        await prisma.commit()
                        return
                    await prisma.send_audio(chunk)

            # Sub-task B: read STT events and manage candidate pause accumulation
            async def _read_events() -> None:
                pause_timer_task: Optional[asyncio.Task] = None
                reprompt_timer_task: Optional[asyncio.Task] = None
                seen_segment_ids: set[str] = set()

                async def _on_pause_expired() -> None:
                    """Candidate paused long enough to confirm complete answer."""
                    try:
                        pause_s = _calculate_pause_timeout(ctx)
                        await asyncio.sleep(pause_s)
                        if not ctx.active or not ctx.accumulated_segments:
                            return
                        logger.info("Candidate answer turn completed for session %s (policy: %s)", ctx.session_id, ctx.endpointing_policy)
                        ctx.metrics.mark_speech_end(ctx.last_speech_time or time.monotonic())
                        await _finalize_turn(ctx)
                    except asyncio.CancelledError:
                        pass

                async def _on_reprompt_check() -> None:
                    """Gentle prompt if no answer starts after 15 seconds."""
                    try:
                        await asyncio.sleep(NO_SPEECH_REPROMPT_S)
                        if (
                            ctx.active
                            and ctx.state_machine.current_state == InterviewState.listening
                            and not ctx.accumulated_segments
                            and not ctx.reprompt_given
                        ):
                            ctx.reprompt_given = True
                            ctx.metrics.record_reprompt()
                            reprompt_text = REPROMPTS.get(ctx.state_machine.language, REPROMPTS["en-IN"])
                            logger.info("Triggering gentle reprompt for session %s", ctx.session_id)
                            await _send_json(ctx, RepromptMessage(text=reprompt_text).__dict__)

                            # Speak reprompt without blocking STT task
                            ctx.state_machine.transition(InterviewState.asking)
                            await _emit_turn_state(ctx)
                            _dispatch_tts(ctx, reprompt_text)
                    except asyncio.CancelledError:
                        pass

                # Arm initial reprompt timer
                reprompt_timer_task = asyncio.create_task(_on_reprompt_check())

                async for evt in prisma.events():
                    if not ctx.active:
                        break

                    now = time.monotonic()

                    if evt.event == "speech_start":
                        ctx.speech_active = True
                        ctx.last_speech_time = now
                        if reprompt_timer_task and not reprompt_timer_task.done():
                            reprompt_timer_task.cancel()
                        if pause_timer_task and not pause_timer_task.done():
                            pause_timer_task.cancel()
                        await _send_json(ctx, ProviderEvent(
                            event="speech_start",
                            detail={"provider": "prisma", "latency_ms": evt.latency_ms},
                        ).__dict__)

                    elif evt.event == "speech_end":
                        ctx.speech_active = False
                        ctx.last_speech_time = now
                        # Arm pause aggregation timer
                        if pause_timer_task and not pause_timer_task.done():
                            pause_timer_task.cancel()
                        pause_timer_task = asyncio.create_task(_on_pause_expired())

                    elif evt.event == "processing":
                        # Gnani documents processing when VAD detects a speech
                        # segment boundary. It does not promise speech_end.
                        ctx.speech_active = False
                        ctx.last_speech_time = now

                    elif evt.event in ("transcript", "transcript-final"):
                        text = evt.transcript.strip()
                        if text:
                            ctx.last_speech_time = now
                            if reprompt_timer_task and not reprompt_timer_task.done():
                                reprompt_timer_task.cancel()

                            if evt.is_final:
                                if evt.segment_id and evt.segment_id in seen_segment_ids:
                                    continue
                                if evt.segment_id:
                                    seen_segment_ids.add(evt.segment_id)
                                # Accumulated segment
                                ctx.accumulated_segments.append(text)
                                await _send_json(ctx, TranscriptMessage(
                                    text=" ".join(ctx.accumulated_segments),
                                    is_final=False,
                                    source="gnani_prisma",
                                    provider_latency_ms=evt.latency_ms,
                                ).__dict__)

                                # Restart pause timer on each final segment
                                if pause_timer_task and not pause_timer_task.done():
                                    pause_timer_task.cancel()
                                pause_timer_task = asyncio.create_task(_on_pause_expired())
                            else:
                                # Intermediate partial transcript
                                interim = " ".join(ctx.accumulated_segments + [text])
                                await _send_json(ctx, TranscriptMessage(
                                    text=interim,
                                    is_final=False,
                                    source="gnani_prisma",
                                    provider_latency_ms=evt.latency_ms,
                                ).__dict__)

                    elif evt.event == "error":
                        err_code = evt.detail.get("code", "stt_error")
                        err_msg = evt.detail.get("message", "Prisma STT encountered an error.")
                        logger.warning("Prisma STT error on session %s: %s", ctx.session_id, err_msg)
                        if "429" in err_msg or "rate" in err_msg.lower():
                            err_code = "rate_limited"
                            err_msg = "Gnani STT rate limit reached. Retrying momentarily."
                        ctx.metrics.record_vad_error()
                        await _send_json(ctx, ErrorMessage(
                            code=err_code,
                            message=err_msg,
                            recoverable=True,
                        ).__dict__)

                    elif evt.event == "close":
                        logger.info("Prisma STT closed upstream on session %s", ctx.session_id)
                        break

                if pause_timer_task and not pause_timer_task.done():
                    pause_timer_task.cancel()
                if reprompt_timer_task and not reprompt_timer_task.done():
                    reprompt_timer_task.cancel()

            feed_task = asyncio.create_task(_feed_audio())
            read_task = asyncio.create_task(_read_events())

            done, pending = await asyncio.wait(
                [feed_task, read_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()


async def _gnani_stt_events(ctx: _SessionContext) -> None:
    """Connect to Prisma STT, stream audio frames, aggregate segments, detect turns."""
    try:
        try:
            await _live_prisma_stt(ctx)
            return
        except Exception as ws_err:
            logger.info("Prisma WS streaming unavailable (%s); bridging via verified Prisma v2.5 REST", ws_err)

        await _fallback_vad_stt(ctx)

    except Exception as exc:
        logger.exception("gnani_stt_events error: %s", exc)
        ctx.metrics.record_connection_failure()
        await _send_json(ctx, ErrorMessage(
            code="stt_connection_error",
            message=f"Could not connect to Gnani Prisma: {exc}",
            recoverable=False,
        ).__dict__)
        ctx.active = False


# ---------------------------------------------------------------------------
# Task 3: Outgoing browser message queue pusher
# ---------------------------------------------------------------------------

async def _outgoing_browser_messages(ws: WebSocket, ctx: _SessionContext) -> None:
    """Send queued control JSON frames and binary audio chunks to client."""
    try:
        while ctx.active or not ctx.control_outgoing.empty() or not ctx.outgoing.empty():
            # Drain prioritized control frames first
            if not ctx.control_outgoing.empty():
                try:
                    ctrl_msg = ctx.control_outgoing.get_nowait()
                    await ws.send_text(ctrl_msg)
                    continue
                except asyncio.QueueEmpty:
                    pass

            if not ctx.outgoing.empty():
                try:
                    item = ctx.outgoing.get_nowait()
                    if isinstance(item, str):
                        await ws.send_text(item)
                    elif isinstance(item, bytes):
                        await ws.send_bytes(item)
                    continue
                except asyncio.QueueEmpty:
                    pass

            if not ctx.active:
                break

            control_task = asyncio.create_task(ctx.control_outgoing.get())
            outgoing_task = asyncio.create_task(ctx.outgoing.get())

            done, pending = await asyncio.wait(
                [control_task, outgoing_task],
                timeout=0.2,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for p in pending:
                p.cancel()

            for completed in done:
                item = completed.result()
                if item is None:
                    continue
                if isinstance(item, str):
                    await ws.send_text(item)
                elif isinstance(item, bytes):
                    await ws.send_bytes(item)
    except WebSocketDisconnect:
        ctx.active = False
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.exception("outgoing_browser_messages error: %s", exc)
        ctx.active = False


# ---------------------------------------------------------------------------
# Turn Finalization & Supervised TTS Dispatch
# ---------------------------------------------------------------------------

async def _finalize_turn(ctx: _SessionContext) -> None:
    """Evaluate candidate answer, persist to store, and dispatch next question."""
    async with ctx.finalizing_lock:
        sm = ctx.state_machine
        if sm.current_state != InterviewState.listening:
            if sm.current_state == InterviewState.asking:
                sm.transition(InterviewState.listening)
                await _emit_turn_state(ctx)
            else:
                return
        if not ctx.accumulated_segments:
            return

        ctx.metrics.mark_endpointing_decision()
        full_transcript = " ".join(ctx.accumulated_segments).strip()
        ctx.accumulated_segments.clear()
        ctx.reprompt_given = False

        if not full_transcript:
            return

        ctx.metrics.mark_final_transcript()
        ctx.metrics.record_transcript_received()

        # Emit final turn transcript message
        await _send_json(ctx, TranscriptMessage(
            text=full_transcript,
            is_final=True,
            is_turn_final=True,
        ).__dict__)

        try:
            sm.transition(InterviewState.transcribing)
            await _emit_turn_state(ctx)

            sm.transition(InterviewState.review)
            await _emit_turn_state(ctx)

            # Process candidate utterance through DialoguePolicy before evaluation
            dialogue_res = sm.process_candidate_utterance(full_transcript, provider_text=full_transcript)
            intent = dialogue_res.get("intent", INTENT_ANSWER)

            if intent in (INTENT_CLARIFICATION, INTENT_REPEAT):
                # Conversational request: stays on current question, zero penalty
                ctx.log_event(f"intent_{intent}", {"transcript": full_transcript})
                await _send_json(ctx, IntentMessage(
                    intent=intent,
                    action=dialogue_res["action"],
                    note=dialogue_res["response_text"],
                ).__dict__)

                sm.transition(InterviewState.feedback)
                await _emit_turn_state(ctx)

                sm.transition(InterviewState.followup)
                await _emit_turn_state(ctx)

                sm.transition(InterviewState.asking)
                await _emit_turn_state(ctx)

                _dispatch_tts(ctx, dialogue_res["response_text"])
                return

            elif intent in (INTENT_SKIP, INTENT_UNCERTAINTY):
                # Candidate skipped or expressed uncertainty
                ctx.log_event(f"intent_{intent}", {"transcript": full_transcript})
                await _send_json(ctx, IntentMessage(
                    intent=intent,
                    action=dialogue_res["action"],
                    note=dialogue_res.get("response_text", ""),
                ).__dict__)

                feedback = dialogue_res["feedback"]
                ctx.metrics.mark_evaluation_done()

                sm.transition(InterviewState.feedback)
                _persist_to_store(ctx)
                await _emit_turn_state(ctx, feedback=feedback)

                if sm.is_complete:
                    sm.transition(InterviewState.completed)
                    _persist_to_store(ctx)
                    ctx.log_event("session_completed", {"answered": sm.question_index})
                    await _emit_turn_state(ctx)
                    await _send_json(ctx, MetricsMessage(data=ctx.metrics.summary()).__dict__)
                    ctx.active = False
                    return

                sm.transition(InterviewState.followup)
                await _emit_turn_state(ctx)

                sm.transition(InterviewState.asking)
                next_q = sm.current_question_text() or ""
                await _emit_turn_state(ctx)

                spoken_text = f"{dialogue_res.get('response_text', '')} {next_q}".strip()
                _dispatch_tts(ctx, spoken_text)
                return

            else:
                # Standard substantive answer
                feedback = dialogue_res["feedback"]
                ctx.metrics.mark_evaluation_done()
                ctx.log_event("candidate_answer_committed", {
                    "transcript": full_transcript,
                    "score": feedback.get("score"),
                    "question_index": sm.question_index,
                })

                sm.transition(InterviewState.feedback)
                _persist_to_store(ctx)
                await _emit_turn_state(ctx, feedback=feedback)

                if sm.is_complete:
                    sm.transition(InterviewState.completed)
                    _persist_to_store(ctx)
                    ctx.log_event("session_completed", {"answered": sm.question_index})
                    await _emit_turn_state(ctx)
                    await _send_json(ctx, MetricsMessage(data=ctx.metrics.summary()).__dict__)
                    ctx.active = False
                    return

                # Prepare follow-up → asking next question
                sm.transition(InterviewState.followup)
                await _emit_turn_state(ctx)

                sm.transition(InterviewState.asking)
                next_question = sm.current_question_text() or ""
                next_spec = sm.current_question_spec()
                await _emit_turn_state(ctx)

                from adaptive import generate_dynamic_followup
                spoken_turn, ack = generate_dynamic_followup(
                    transcript=full_transcript,
                    feedback=feedback,
                    next_question_spec=next_spec,
                    language=sm.language,
                    question_index=sm.question_index - 1,
                    track=sm.track,
                )
                # Supervised TTS dispatch — dynamically speaks acknowledgment + responsive follow-up
                _dispatch_tts(ctx, spoken_turn)

        except InvalidTransition as exc:
            logger.warning("Turn finalization invalid transition: %s", exc)
        except Exception as exc:
            logger.exception("Turn finalization error: %s", exc)
            await _send_json(ctx, ErrorMessage(
                code="evaluation_error",
                message="Answer evaluation failed.",
                recoverable=True,
            ).__dict__)


def _dispatch_tts(ctx: _SessionContext, text: str) -> asyncio.Task:
    """Launch supervised TTS streaming task for a question or reprompt."""
    gen_id = ctx.new_generation()
    if ctx.active_tts_task and not ctx.active_tts_task.done():
        ctx.active_tts_task.cancel()

    async def _runner():
        try:
            ctx.metrics.mark_tts_dispatched()
            await _play_tts(ctx, text, gen_id)
            # When TTS completes without being interrupted or superseded
            if (
                ctx.active
                and ctx.generation_id == gen_id
                and ctx.state_machine.current_state == InterviewState.asking
            ):
                ctx.state_machine.transition(InterviewState.listening)
                await _emit_turn_state(ctx)
        except asyncio.CancelledError:
            # Expected on barge-in interruption or session end
            pass
        except Exception as exc:
            logger.warning("Error in TTS synthesis runner (gen %s): %s", gen_id, exc)

    task = asyncio.create_task(_runner(), name=f"tts-gen-{gen_id}")
    ctx.active_tts_task = task
    return task


async def _play_tts(ctx: _SessionContext, text: str, gen_id: Optional[int] = None) -> None:
    """Stream synthesized audio chunks from Timbre TTS to client, with verified REST fallback."""
    language = ctx.state_machine.language
    active_gen_id = gen_id if gen_id is not None else ctx.generation_id
    try:
        try:
            async with TimbreStreamingClient(language=language) as tts:
                ctx.metrics.record_tts_call()
                first_chunk = True
                voice = VOICE.get(language, "Pranav")

                async for chunk in tts.synthesize(text):
                    # Barge-in guard: discard if generation changed or session ended
                    if not ctx.active or ctx.generation_id != active_gen_id:
                        await tts.interrupt()
                        return

                    if chunk.data:
                        if first_chunk:
                            ctx.metrics.mark_first_tts_audio()
                            ctx.metrics.mark_playback_start()
                            await _send_json(ctx, TTSAudioMeta(
                                voice=voice,
                                language=language,
                                generation_id=active_gen_id,
                                sample_rate=24000,
                                encoding="pcm_s16le",
                            ).__dict__)
                            first_chunk = False

                        # Forward binary audio frame to client
                        await _send_binary(ctx, chunk.data)

                    if chunk.is_last:
                        break
                if not first_chunk and ctx.generation_id == active_gen_id:
                    await _send_tts_complete(ctx, active_gen_id)
                return
        except Exception as ws_err:
            logger.info("Timbre WS streaming unavailable (%s); bridging via verified Timbre v2.5 REST", ws_err)

        # Fallback to verified GnaniClient REST synthesis
        gc = GnaniClient()
        if gc.enabled:
            ctx.metrics.record_tts_call()
            voice = VOICE.get(language, "Pranav")
            audio_bytes = await asyncio.to_thread(gc.synthesize, text, language)
            if not ctx.active or ctx.generation_id != active_gen_id:
                return
            ctx.metrics.mark_first_tts_audio()
            ctx.metrics.mark_playback_start()
            await _send_json(ctx, TTSAudioMeta(
                voice=voice,
                language=language,
                generation_id=active_gen_id,
                sample_rate=24000,
                encoding="pcm_s16le",
            ).__dict__)
            await _send_binary(ctx, audio_bytes)
            await _send_tts_complete(ctx, active_gen_id)
            return

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("Timbre TTS synthesis failed: %s", exc)
        await _send_json(ctx, ErrorMessage(
            code="tts_error",
            message="Speech synthesis failed; continuing with text question.",
            recoverable=True,
        ).__dict__)


# ---------------------------------------------------------------------------
# WebSocket Endpoint: /ws/interview
# ---------------------------------------------------------------------------

@ws_router.websocket("/ws/interview")
async def interview_ws(ws: WebSocket) -> None:
    """Authoritative hands-free WebSocket interview endpoint."""
    from auth_service import auth_required
    origin = ws.headers.get("origin")
    host = ws.headers.get("host", "")
    if origin and urlparse(origin).netloc != host:
        await ws.close(code=1008, reason="Origin mismatch")
        return
    peer = ws.client.host if ws.client else ""
    local_hosts = {"localhost", "127.0.0.1", "[::1]", "testserver"}
    local_peers = {"localhost", "127.0.0.1", "::1", "testclient"}
    if (host.split(":")[0] not in local_hosts or peer not in local_peers) and \
            not auth_required() and os.getenv("IM_WS_ALLOW_REMOTE_UNAUTHENTICATED") != "1":
        await ws.close(code=1008, reason="Remote streaming requires authentication")
        return
    protocol_version = ws.query_params.get("protocol_version", PROTOCOL_VERSION)
    if protocol_version != PROTOCOL_VERSION:
        await ws.close(code=1008, reason=f"Unsupported protocol version: {protocol_version}")
        return

    await ws.accept()

    # Wait for session_start JSON handshake
    try:
        raw_init = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        init = parse_message(raw_init, validate_version=True)
    except Exception:
        await ws.close(code=1008, reason="Handshake parse error")
        return

    if init.type not in ("session_start", "session_resume"):
        await ws.close(code=1008, reason="First message must be session_start or session_resume")
        return

    track = getattr(init, "track", "agentic")
    language = getattr(init, "language", "en-IN")
    consent = getattr(init, "consent_given", False)
    stt_model = getattr(init, "stt_model", "prisma-v2.5")
    requested_session_id = getattr(init, "session_id", None)
    endpointing_policy = getattr(init, "endpointing_policy", "fixed")

    # Authentication and Session Ownership Verification
    from auth_service import auth_required, parse_token
    from main import STORE

    owner_id: str | None = None
    if auth_required():
        token = ws.query_params.get("token") or getattr(init, "token", None)
        if not token:
            await ws.send_text(ErrorMessage(
                code="unauthorized",
                message="Authentication required when IM_AUTH_REQUIRED=true.",
                recoverable=False,
            ).to_json())
            await ws.close(code=1008, reason="Authentication required")
            return
        try:
            claims = parse_token(token, STORE)
            owner_id = claims["sub"]
        except Exception as auth_err:
            await ws.send_text(ErrorMessage(
                code="unauthorized",
                message=f"Invalid or expired token: {auth_err}",
                recoverable=False,
            ).to_json())
            await ws.close(code=1008, reason="Invalid token")
            return

    # Check for existing session resume
    is_resume = init.type == "session_resume"
    existing_record = None
    if requested_session_id and STORE:
        try:
            with STORE.connect() as db:
                row = db.execute("SELECT owner_id, state_json FROM interviews WHERE id=?", (requested_session_id,)).fetchone()
                if row:
                    stored_owner = row["owner_id"]
                    if stored_owner != owner_id:
                        await ws.send_text(ErrorMessage(
                            code="forbidden",
                            message="Cannot access a session owned by another user.",
                            recoverable=False,
                        ).to_json())
                        await ws.close(code=1008, reason="Forbidden")
                        return
                    existing_record = {"state": json.loads(row["state_json"])}
                    is_resume = True
                    stored_state = existing_record["state"]
                    track = stored_state.get("track", track)
                    language = stored_state.get("language", language)
                    consent = True
        except Exception as store_err:
            logger.warning("Session ownership verification error: %s", store_err)

    if not consent and not is_resume:
        await ws.send_text(ErrorMessage(
            code="consent_required",
            message="Explicit audio consent is required before streaming to Gnani.",
            recoverable=False,
        ).to_json())
        await ws.close(code=1008, reason="Consent required")
        return

    session_id = requested_session_id or str(uuid.uuid4())

    target_questions = getattr(init, "target_questions", 3) or 3
    role = getattr(init, "role", "Software Engineer") or "Software Engineer"
    resume_text = getattr(init, "resume_text", None)
    github_repo = getattr(init, "github_repo", None)

    from personalization import INTRODUCE_YOURSELF_QUESTION, personalize_question_seed
    # Question 1 is ALWAYS the introduction question
    initial_seed = INTRODUCE_YOURSELF_QUESTION

    # Pre-analyze GitHub profile or resume for Question 2
    project_seed = None
    if resume_text or github_repo:
        project_seed = personalize_question_seed(
            track=track,
            language=language,
            resume_text=resume_text,
            github_repo=github_repo,
        )
        if project_seed and "text" in project_seed:
            project_seed[language] = project_seed["text"]

    try:
        ctx = _SessionContext(
            session_id=session_id,
            track=track,
            language=language,
            stt_model=stt_model,
            consent=consent,
            store=STORE,
            owner_id=owner_id,
            endpointing_policy=endpointing_policy,
            initial_seed=initial_seed,
            max_questions=target_questions,
            role=role,
        )
        if project_seed:
            ctx.state_machine.personalized_seed = project_seed
    except ValueError as exc:
        await ws.send_text(ErrorMessage(
            code="invalid_config", message=str(exc), recoverable=False
        ).to_json())
        await ws.close(code=1008, reason="Invalid config")
        return

    sm = ctx.state_machine

    if is_resume and existing_record:
        state_data = existing_record["state"]
        sm.question_index = state_data.get("question_index", 0)
        sm.answers = state_data.get("answers", [])
        stored_state_val = state_data.get("current_state", "asking")
        try:
            sm._state = InterviewState(stored_state_val)
        except Exception:
            sm._state = InterviewState.asking
        ctx.log_event("session_resumed", {"answered": sm.question_index, "current_state": sm.current_state.value})
    else:
        ctx.metrics.mark_session_start()
        sm.transition(InterviewState.asking)
        ctx.log_event("session_started", {"track": track, "language": language})

    _persist_to_store(ctx)

    current_q = sm.current_question_text() or ""

    # Send session acknowledgement
    await ws.send_text(SessionAck(
        session_id=ctx.session_id,
        question=current_q,
        question_number=min(sm.question_index + 1, sm.MAX_QUESTIONS),
        total_questions=sm.MAX_QUESTIONS,
        status="resumed" if is_resume else "ok",
    ).to_json())

    await _emit_turn_state(ctx)

    # Launch concurrent pipeline tasks
    tasks: list[asyncio.Task] = []
    try:
        tasks = [
            asyncio.create_task(_browser_audio_ingest(ws, ctx), name="ingest"),
            asyncio.create_task(_gnani_stt_events(ctx), name="stt"),
            asyncio.create_task(_outgoing_browser_messages(ws, ctx), name="outgoing"),
        ]

        # Autonomous start: Speak active question if in asking state
        if current_q and sm.current_state == InterviewState.asking:
            _dispatch_tts(ctx, current_q)

        # Maintain session loop until complete or session limit reached
        done, _ = await asyncio.wait(
            tasks,
            timeout=MAX_SESSION_DURATION_S,
            return_when=asyncio.FIRST_COMPLETED,
        )
        ctx.active = False

    except asyncio.CancelledError:
        ctx.active = False
    except Exception as exc:
        logger.exception("interview_ws error: %s", exc)
        ctx.active = False
    finally:
        ctx.active = False
        if ctx.active_tts_task and not ctx.active_tts_task.done():
            ctx.active_tts_task.cancel()
        for t in tasks:
            if not t.done():
                t.cancel()
        _persist_to_store(ctx)
        try:
            await ws.send_text(MetricsMessage(data=ctx.metrics.summary()).to_json())
            await ws.close(code=1000)
        except Exception:
            pass
