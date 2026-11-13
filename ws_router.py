"""FastAPI WebSocket router for the realtime voice interview pipeline.

Endpoint: ``/ws/interview``

Three concurrent async tasks per session:
  1. ``_browser_audio_ingest`` — reads PCM frames + JSON control from the browser
  2. ``_gnani_stt_events``    — forwards STT events from Prisma to the outgoing queue
  3. ``_outgoing_browser_messages`` — drains the outgoing queue to the browser

All tasks are cancelled on disconnect, timeout or session-end. The Gnani API
key never leaves the server.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ws_protocol import (
    PROTOCOL_VERSION,
    MAX_QUEUE_DEPTH,
    MAX_SESSION_DURATION_S,
    PCM_FRAME_BYTES,
    SessionStart,
    SessionAck,
    ProviderEvent,
    ErrorMessage,
    TranscriptMessage,
    TurnStateMessage,
    TTSAudioMeta,
    MetricsMessage,
    PingMessage,
    PongMessage,
    parse_message,
    is_pcm_frame,
    _next_seq,
)
from interview_state import InterviewState, InterviewStateMachine, InvalidTransition
from gnani_streaming import PrismaStreamingClient, TimbreStreamingClient
from gnani import VOICE
from metrics import SessionMetrics

logger = logging.getLogger(__name__)

ws_router = APIRouter()


class _SessionContext:
    """Mutable per-session state shared across the three tasks."""

    def __init__(self, track: str, language: str, stt_model: str, consent: bool) -> None:
        self.session_id = str(uuid.uuid4())
        self.state_machine = InterviewStateMachine(track, language)
        self.state_machine.consent_given = consent
        self.stt_model = stt_model
        self.metrics = SessionMetrics()
        self.seq: int = 0  # outgoing sequence counter

        # Bounded queues
        self.audio_to_stt: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=MAX_QUEUE_DEPTH)
        self.outgoing: asyncio.Queue[str | bytes] = asyncio.Queue(maxsize=MAX_QUEUE_DEPTH)

        self.active = True
        self.browser_disconnected = False

    def next_seq(self) -> int:
        self.seq = _next_seq(self.seq)
        return self.seq


async def _enqueue_or_drop(
    queue: asyncio.Queue,
    item,
    ctx: _SessionContext,
    label: str = "outgoing",
) -> None:
    """Put *item* on *queue*; drop oldest if full (slow-client detection)."""
    if queue.full():
        try:
            queue.get_nowait()
            ctx.metrics.record_dropped_frame()
            logger.debug("Slow client: dropped oldest %s message", label)
        except asyncio.QueueEmpty:
            pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        ctx.metrics.record_dropped_frame()


async def _send_json(ctx: _SessionContext, msg_dict: dict) -> None:
    """Enqueue a JSON string for delivery to the browser."""
    msg_dict["sequence_number"] = ctx.next_seq()
    msg_dict["protocol_version"] = PROTOCOL_VERSION
    msg_dict["timestamp_ms"] = int(time.time() * 1000)
    await _enqueue_or_drop(ctx.outgoing, json.dumps(msg_dict, ensure_ascii=False), ctx)


async def _send_binary(ctx: _SessionContext, data: bytes) -> None:
    """Enqueue binary audio data for delivery to the browser."""
    await _enqueue_or_drop(ctx.outgoing, data, ctx)


# ---------------------------------------------------------------------------
# Task 1: browser → server (audio + control)
# ---------------------------------------------------------------------------

async def _browser_audio_ingest(ws: WebSocket, ctx: _SessionContext) -> None:
    """Read from the browser WebSocket — PCM binary frames or JSON control."""
    try:
        while ctx.active:
            raw = await ws.receive()
            if raw.get("type") == "websocket.disconnect":
                ctx.browser_disconnected = True
                ctx.active = False
                return

            # Binary PCM frame
            if "bytes" in raw and raw["bytes"] is not None:
                frame = raw["bytes"]
                if is_pcm_frame(frame):
                    await _enqueue_or_drop(ctx.audio_to_stt, frame, ctx, "stt-audio")
                    ctx.metrics.record_frame_sent()
                else:
                    await _send_json(ctx, ErrorMessage(
                        code="invalid_audio_frame", message="Expected 1024-byte PCM frame",
                        recoverable=True,
                    ).__dict__)
                continue

            # JSON control
            text = raw.get("text", "")
            if not text:
                continue

            try:
                msg = parse_message(text)
            except Exception:
                await _send_json(ctx, ErrorMessage(
                    code="parse_error", message="Malformed JSON", recoverable=True,
                ).__dict__)
                continue

            if msg.type == "ping":
                await _send_json(ctx, PongMessage(turn_id=msg.turn_id).__dict__)

            elif msg.type == "session_start":
                # Already started — just ack again
                await _send_json(ctx, SessionAck(
                    session_id=ctx.session_id,
                    question=ctx.state_machine.current_question_text() or "",
                    question_number=ctx.state_machine.question_index + 1,
                    total_questions=ctx.state_machine.MAX_QUESTIONS,
                ).__dict__)

            elif msg.type == "end_audio":
                # User stopped talking
                ctx.metrics.mark_speech_end()
                await ctx.audio_to_stt.put(None)  # EOF sentinel

    except WebSocketDisconnect:
        ctx.browser_disconnected = True
        ctx.active = False
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("browser_audio_ingest error: %s", exc)
        ctx.active = False


# ---------------------------------------------------------------------------
# Task 2: Prisma STT event loop
# ---------------------------------------------------------------------------

async def _gnani_stt_events(ctx: _SessionContext) -> None:
    """Connect to Prisma, forward audio, and relay STT events to outgoing."""
    try:
        async with PrismaStreamingClient(
            language_code=("indic-auto" if ctx.stt_model == "prisma-v3.0"
                           else ctx.state_machine.language),
            model=ctx.stt_model,
        ) as prisma:
            ctx.metrics.record_connection_success()
            ctx.metrics.record_stt_call()

            await _send_json(ctx, ProviderEvent(
                event="connected",
                detail={"provider": "prisma", "model": ctx.stt_model},
            ).__dict__)

            # Two sub-tasks: audio feeder and event reader
            async def _feed_audio() -> None:
                while ctx.active:
                    try:
                        chunk = await asyncio.wait_for(ctx.audio_to_stt.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    if chunk is None:
                        await prisma.send_eof()
                        return
                    await prisma.send_audio(chunk)

            async def _read_events() -> None:
                async for evt in prisma.events():
                    if not ctx.active:
                        return
                    await _send_json(ctx, ProviderEvent(
                        event=evt.event,
                        detail={
                            "transcript": evt.transcript,
                            "is_final": evt.is_final,
                            "latency_ms": evt.latency_ms,
                        },
                    ).__dict__)

                    if evt.event == "speech_start":
                        ctx.metrics.mark_provider_processing()

                    if evt.is_final and evt.transcript.strip():
                        ctx.metrics.mark_final_transcript()
                        ctx.metrics.record_transcript_received()
                        ctx.state_machine.provider_transcript = evt.transcript.strip()

                        await _send_json(ctx, TranscriptMessage(
                            text=evt.transcript.strip(),
                            is_final=True,
                            provider_latency_ms=evt.latency_ms,
                        ).__dict__)

                        # The candidate reviews this text before the existing REST
                        # session scores the edited answer. Never score here.
                        if ctx.state_machine.current_state == InterviewState.listening:
                            ctx.state_machine.transition(InterviewState.transcribing)
                            ctx.state_machine.transition(InterviewState.review)
                        await _send_json(ctx, TurnStateMessage(state="review").__dict__)

                    if evt.event in ("error", "close"):
                        if evt.event == "error":
                            ctx.metrics.record_vad_error()
                        return

            feeder = asyncio.create_task(_feed_audio())
            reader = asyncio.create_task(_read_events())
            try:
                await asyncio.gather(feeder, reader)
            finally:
                feeder.cancel()
                reader.cancel()
                try:
                    await feeder
                except (asyncio.CancelledError, Exception):
                    pass
                try:
                    await reader
                except (asyncio.CancelledError, Exception):
                    pass

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        ctx.metrics.record_connection_failure()
        logger.exception("gnani_stt_events error: %s", exc)
        await _send_json(ctx, ErrorMessage(
            code="stt_connection_error",
            message="STT provider connection failed.",
            recoverable=False,
        ).__dict__)
        ctx.active = False


async def _process_transcript(ctx: _SessionContext) -> None:
    """Run scoring and optionally trigger TTS for the next question."""
    sm = ctx.state_machine
    transcript = sm.provider_transcript
    if not transcript:
        return

    try:
        sm.transition(InterviewState.transcribing)
        sm.transition(InterviewState.review)

        ctx.metrics.mark_response_gen_start()
        feedback = sm.advance(transcript)

        sm.transition(InterviewState.feedback)

        await _send_json(ctx, TurnStateMessage(
            state="feedback",
            question_number=sm.question_index,
            feedback=feedback,
        ).__dict__)

        if sm.is_complete:
            sm.transition(InterviewState.completed) if InterviewState.completed in \
                {InterviewState.completed} else None
            # completed is a valid transition from feedback
            try:
                sm.transition(InterviewState.completed)
            except InvalidTransition:
                pass
            await _send_json(ctx, TurnStateMessage(state="completed").__dict__)
            await _send_json(ctx, MetricsMessage(data=ctx.metrics.summary()).__dict__)
            ctx.active = False
        else:
            # Move to followup → asking and do TTS for next question
            sm.transition(InterviewState.followup)
            sm.transition(InterviewState.asking)

            next_q = sm.current_question_text()
            if next_q:
                await _send_json(ctx, TurnStateMessage(
                    state="asking",
                    question=next_q,
                    question_number=sm.question_index + 1,
                ).__dict__)
                await _play_tts(ctx, next_q)
                sm.transition(InterviewState.listening)
                await _send_json(ctx, TurnStateMessage(state="listening").__dict__)

    except InvalidTransition as exc:
        logger.warning("State transition error: %s", exc)
    except Exception as exc:
        logger.exception("process_transcript error: %s", exc)
        await _send_json(ctx, ErrorMessage(
            code="processing_error",
            message="Failed to process transcript.",
            recoverable=False,
        ).__dict__)


async def _play_tts(ctx: _SessionContext, text: str) -> None:
    """Stream TTS audio for *text* to the browser."""
    language = ctx.state_machine.language
    try:
        async with TimbreStreamingClient(language=language) as tts:
            ctx.metrics.record_tts_call()
            first_chunk = True
            total_bytes = 0
            async for chunk in tts.synthesize(text):
                if not ctx.active:
                    await tts.interrupt()
                    return
                if chunk.data:
                    if first_chunk:
                        ctx.metrics.mark_first_tts_audio()
                        ctx.metrics.mark_playback_start()
                        voice = VOICE.get(language, "Pranav")
                        await _send_json(ctx, TTSAudioMeta(
                            voice=voice,
                            language=language,
                            size_bytes=len(chunk.data),
                        ).__dict__)
                        first_chunk = False
                    await _send_binary(ctx, chunk.data)
                    total_bytes += len(chunk.data)
                if chunk.is_last:
                    break
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("TTS playback error: %s", exc)
        await _send_json(ctx, ErrorMessage(
            code="tts_error",
            message="TTS playback failed.",
            recoverable=True,
        ).__dict__)


# ---------------------------------------------------------------------------
# Task 3: outgoing queue → browser
# ---------------------------------------------------------------------------

async def _outgoing_browser_messages(ws: WebSocket, ctx: _SessionContext) -> None:
    """Drain the outgoing queue and push messages to the browser."""
    try:
        while ctx.active or not ctx.outgoing.empty():
            try:
                item = await asyncio.wait_for(ctx.outgoing.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if not ctx.active:
                    break
                continue
            try:
                if isinstance(item, bytes):
                    await ws.send_bytes(item)
                else:
                    await ws.send_text(item)
            except (WebSocketDisconnect, RuntimeError):
                ctx.active = False
                return
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("outgoing_browser_messages error: %s", exc)
        ctx.active = False


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@ws_router.websocket("/ws/interview")
async def interview_ws(ws: WebSocket) -> None:
    # This prototype has no per-user WebSocket authentication. Keep provider
    # credits inaccessible from a public network unless explicitly opted in.
    peer = ws.client.host if ws.client else ""
    if peer not in {"127.0.0.1", "::1", "localhost", "testclient"} and \
            os.getenv("INTERVIEWMIRROR_WS_ALLOW_REMOTE") != "1":
        await ws.close(code=1008, reason="Remote streaming disabled")
        return
    origin = ws.headers.get("origin")
    host = ws.headers.get("host")
    if origin and host:
        from urllib.parse import urlparse
        if urlparse(origin).netloc != host:
            await ws.close(code=1008, reason="Origin mismatch")
            return
    pv = ws.query_params.get("protocol_version")
    if pv is not None and pv != PROTOCOL_VERSION:
        await ws.close(code=1008, reason=f"Unsupported protocol version: {pv}")
        return
    await ws.accept()

    # Wait for the initial session_start message
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await ws.close(code=1008, reason="Expected session_start")
        return

    try:
        init = parse_message(raw)
    except Exception:
        await ws.close(code=1008, reason="Invalid session_start")
        return

    if init.type != "session_start":
        await ws.close(code=1008, reason="First message must be session_start")
        return

    if getattr(init, "protocol_version", PROTOCOL_VERSION) != PROTOCOL_VERSION:
        await ws.send_text(ErrorMessage(
            code="invalid_protocol_version",
            message=f"Unsupported protocol version: {init.protocol_version}",
            recoverable=False,
        ).to_json())
        await ws.close(code=1008, reason="Unsupported protocol version")
        return

    # Extract session parameters
    track = getattr(init, "track", "agentic")
    language = getattr(init, "language", "en-IN")
    consent = getattr(init, "consent_given", False)
    stt_model = getattr(init, "stt_model", "prisma-v2.5")

    if not consent:
        await ws.send_text(ErrorMessage(
            code="consent_required",
            message="Explicit consent is required before forwarding audio to Gnani.",
            recoverable=False,
        ).to_json())
        await ws.close(code=1008, reason="Consent required")
        return

    try:
        ctx = _SessionContext(track, language, stt_model, consent)
    except ValueError as exc:
        await ws.send_text(ErrorMessage(
            code="invalid_config",
            message=str(exc),
            recoverable=False,
        ).to_json())
        await ws.close(code=1008, reason="Invalid config")
        return

    ctx.metrics.mark_session_start()

    # Transition to asking and send ack
    sm = ctx.state_machine
    sm.transition(InterviewState.asking)

    first_question = sm.current_question_text() or ""
    await ws.send_text(SessionAck(
        session_id=ctx.session_id,
        question=first_question,
        question_number=1,
        total_questions=sm.MAX_QUESTIONS,
    ).to_json())

    # The existing REST session owns the question and answer state. This
    # connection supplies live transcription only; the browser already has
    # the current question and requests its audio through /api/speak.

    # Launch the three tasks + session timeout
    tasks: list[asyncio.Task] = []
    try:
        tasks = [
            asyncio.create_task(_browser_audio_ingest(ws, ctx), name="ingest"),
            asyncio.create_task(_gnani_stt_events(ctx), name="stt"),
            asyncio.create_task(_outgoing_browser_messages(ws, ctx), name="outgoing"),
        ]

        sm.transition(InterviewState.listening)
        await _send_json(ctx, TurnStateMessage(state="listening").__dict__)

        # Wait for any task to finish or session timeout
        done, _pending = await asyncio.wait(
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
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if not ctx.browser_disconnected:
            try:
                await ws.send_text(MetricsMessage(data=ctx.metrics.summary()).to_json())
                await ws.close()
            except (WebSocketDisconnect, RuntimeError):
                pass
