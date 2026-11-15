"""Gnani streaming WebSocket adapters — Prisma STT and Timbre TTS.

Official endpoints:
  - Prisma WebSocket: wss://api.vachana.ai/stt/v3/stream
    Configuration in connection headers; exact 1,024-byte PCM frames.
    Provider sends type, text, is_final, segment_id, request_id.
    {"type":"commit"} is the documented explicit flush control.
  - Timbre WebSocket: wss://api.vachana.ai/api/v1/tts
    Audio chunks arrive as base64 inside JSON (either top-level or data.audio),
    terminated by type="complete" or is_final=true.
    Supports low-latency raw signed 16-bit PCM (pcm_s16le).

Both clients are async context managers with cancellation and clean teardown.
The Gnani API key remains strictly server-side.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import websockets
import websockets.exceptions

from gnani import VOICE

logger = logging.getLogger(__name__)

# Documented verified endpoints
PRISMA_WS_URL = "wss://api.vachana.ai/stt/v3/stream"
TIMBRE_WS_URL = "wss://api.vachana.ai/api/v1/tts"

# Supported Prisma models
_PRISMA_MODELS = {"prisma-v2.5", "prisma-v3.0"}

PCM_FRAME_BYTES = 1024  # 512 samples × 2 bytes signed 16-bit LE PCM


@dataclass
class PrismaEvent:
    """Parsed event from the Prisma STT WebSocket."""
    event: str            # connected, speech_start, speech_end, transcript, error, close
    transcript: str = ""
    is_final: bool = False
    language_code: str = ""
    segment_id: str = ""
    request_id: str = ""
    detail: dict = field(default_factory=dict)
    latency_ms: float = 0.0


class PrismaStreamingClient:
    """Realtime Prisma STT over WebSocket (wss://api.vachana.ai/stt/v3/stream).

    Configuration is transmitted via connection headers.
    Audio frames are sent as exact 1,024-byte PCM binary chunks.
    {"type":"commit"} is the documented explicit flush control.
    """

    def __init__(
        self,
        language_code: str = "en-IN",
        model: str = "prisma-v2.5",
        *,
        api_key: Optional[str] = None,
        silence_timeout_s: float = 1.5,
        sample_rate: int = 16000,
    ) -> None:
        if model not in _PRISMA_MODELS:
            raise ValueError(f"Unsupported Prisma model: {model}")
        self._api_key = (api_key or os.getenv("GNANI_API_KEY", "")).strip()
        if not self._api_key:
            raise RuntimeError("GNANI_API_KEY is required for Prisma streaming.")
        self.language_code = language_code
        self.model = model
        self.sample_rate = sample_rate
        self.silence_timeout_s = silence_timeout_s
        self._ws: Optional[Any] = None
        self._closed = False
        self._send_ts: float = 0.0
        self._frames_sent: int = 0

    @property
    def ws_url(self) -> str:
        return PRISMA_WS_URL

    async def __aenter__(self) -> "PrismaStreamingClient":
        # Documented protocol: configuration is sent in connection headers
        headers = {
            "X-API-Key-ID": self._api_key,
            "language_code": self.language_code,
            "model": self.model,
            "format": "codemix" if self.model == "prisma-v3.0" else "transcribe",
            "x-sample-rate": str(self.sample_rate),
            "x-min-silence-ms": str(int(self.silence_timeout_s * 1000)),
            "x-vad-threshold": "0.5",
            "x-min-speech-ms": "250",
            "x-min-segment-ms": "500",
        }
        try:
            self._ws = await websockets.connect(
                PRISMA_WS_URL,
                additional_headers=headers,
                max_size=2**20,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )
        except Exception as exc:
            raise RuntimeError(f"Prisma WS connect failed: {exc}") from exc

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._closed = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def send_audio(self, pcm_data: bytes) -> None:
        """Forward raw PCM frames (1024 bytes each) to Prisma."""
        if self._ws is None or self._closed:
            return
        offset = 0
        while offset < len(pcm_data):
            chunk = pcm_data[offset:offset + PCM_FRAME_BYTES]
            try:
                await self._ws.send(chunk)
                self._frames_sent += 1
                self._send_ts = time.monotonic()
            except websockets.exceptions.ConnectionClosed:
                self._closed = True
                return
            offset += PCM_FRAME_BYTES

    async def commit(self) -> None:
        """Send documented explicit flush control: {"type": "commit"}."""
        if self._ws is None or self._closed:
            return
        try:
            await self._ws.send(json.dumps({"type": "commit"}))
        except websockets.exceptions.ConnectionClosed:
            self._closed = True

    async def send_eof(self) -> None:
        """Commit remaining audio and signal completion."""
        await self.commit()

    async def events(self) -> AsyncIterator[PrismaEvent]:
        """Yield parsed events from Prisma STT stream.

        Handles provider type, text, is_final, segment_id, and request_id.
        """
        if self._ws is None:
            return
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue  # unexpected binary message; skip
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Documented fields: type, text, is_final
                msg_type = data.get("type", data.get("event", "transcript"))
                transcript_text = data.get("text", data.get("transcript", ""))
                is_final = bool(data.get("is_final", msg_type in ("transcript-final", "final")))

                now = time.monotonic()
                latency = (now - self._send_ts) * 1000 if self._send_ts > 0 else 0.0

                evt = PrismaEvent(
                    event=msg_type,
                    transcript=transcript_text,
                    is_final=is_final,
                    language_code=data.get("language_code", self.language_code),
                    segment_id=str(data.get("segment_id", "")),
                    request_id=str(data.get("request_id", "")),
                    detail=data,
                    latency_ms=round(latency, 2),
                )

                # Verify configuration if returned on connect
                if msg_type == "connected":
                    server_model = data.get("model", "")
                    if server_model and server_model != self.model:
                        logger.warning(
                            "Prisma model mismatch: requested %s, got %s",
                            self.model, server_model,
                        )

                yield evt

                # Gnani can emit a recoverable error and keep the session
                # open. Only a close event (or WebSocket close) ends reading.
                if msg_type == "close":
                    break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._closed = True


# ---------------------------------------------------------------------------
# Timbre streaming TTS
# ---------------------------------------------------------------------------

@dataclass
class TimbreAudioChunk:
    """Decoded audio chunk from Timbre TTS."""
    data: bytes
    is_last: bool = False
    chunk_index: int = 0
    detail: dict = field(default_factory=dict)


class TimbreStreamingClient:
    """Realtime Timbre TTS over WebSocket (wss://api.vachana.ai/api/v1/tts).

    Audio chunks arrive as base64 inside JSON (nested data.audio or top-level),
    terminated by type="complete" or is_final=true.
    Barge-in / cancellation cancels the stream using supported task cancellation.
    """

    def __init__(
        self,
        language: str = "en-IN",
        *,
        api_key: Optional[str] = None,
        voice: Optional[str] = None,
        sample_rate: int = 24000,
        container: str = "raw",
    ) -> None:
        self._api_key = (api_key or os.getenv("GNANI_API_KEY", "")).strip()
        if not self._api_key:
            raise RuntimeError("GNANI_API_KEY is required for Timbre streaming.")
        self.language = language
        self.voice = voice or VOICE.get(language, "Pranav")
        self.sample_rate = sample_rate
        self.container = container
        self._ws: Optional[Any] = None
        self._closed = False
        self._interrupted = False

    @property
    def ws_url(self) -> str:
        return TIMBRE_WS_URL

    async def __aenter__(self) -> "TimbreStreamingClient":
        headers = {
            "X-API-Key-ID": self._api_key,
        }
        try:
            self._ws = await websockets.connect(
                TIMBRE_WS_URL,
                additional_headers=headers,
                max_size=2**22,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )
        except Exception as exc:
            raise RuntimeError(f"Timbre WS connect failed: {exc}") from exc
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._closed = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def synthesize(self, text: str) -> AsyncIterator[TimbreAudioChunk]:
        """Request synthesis for text and yield decoded audio chunks.

        Decodes base64 payload inside JSON chunks (supporting nested data.audio
        as well as top-level audio); finishes on type='complete' or is_final=true.
        """
        if self._ws is None or self._closed:
            return
        self._interrupted = False

        request = {
            "text": text.strip(),
            "model": "timbre-v2.5",
            "voice": self.voice,
            "language": self.language,
            "speed": 1.0,
            "audio_config": {
                "encoding": "pcm_s16le",
                "container": self.container,
                "num_channels": 1,
                "sample_rate": self.sample_rate,
                "sample_width": 2,
            },
        }
        try:
            await self._ws.send(json.dumps(request))
        except websockets.exceptions.ConnectionClosed:
            self._closed = True
            return

        expected_chunk_index = 0
        try:
            async for raw in self._ws:
                if self._interrupted or self._closed:
                    break
                if isinstance(raw, bytes):
                    # Provider sent raw binary audio bytes
                    yield TimbreAudioChunk(
                        data=raw,
                        is_last=False,
                        chunk_index=expected_chunk_index,
                    )
                    expected_chunk_index += 1
                else:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = data.get("type", data.get("event", ""))

                    # Extract base64 audio and metadata from either nested data dict or top-level
                    b64_audio = None
                    chunk_index = expected_chunk_index
                    is_final = False

                    data_payload = data.get("data")
                    if isinstance(data_payload, dict):
                        b64_audio = (
                            data_payload.get("audio")
                            or data_payload.get("audio_content")
                            or data_payload.get("chunk")
                        )
                        chunk_index = data_payload.get("chunk_index", expected_chunk_index)
                        is_final = bool(data_payload.get("is_final", False))
                    else:
                        b64_audio = data.get("audio") or data.get("audio_content") or data.get("chunk")
                        chunk_index = data.get("chunk_index", expected_chunk_index)
                        is_final = bool(data.get("is_final", False))

                    if b64_audio:
                        try:
                            audio_bytes = base64.b64decode(b64_audio)
                            yield TimbreAudioChunk(
                                data=audio_bytes,
                                is_last=False,
                                chunk_index=chunk_index,
                                detail=data,
                            )
                            expected_chunk_index = chunk_index + 1
                        except Exception as exc:
                            logger.warning("Failed to decode Timbre base64 chunk: %s", exc)

                    if msg_type in ("complete", "done", "end") or is_final:
                        yield TimbreAudioChunk(
                            data=b"",
                            is_last=True,
                            chunk_index=expected_chunk_index,
                            detail=data,
                        )
                        break
                    elif msg_type == "error":
                        err_msg = data.get("message", "Unknown Timbre error")
                        logger.error("Timbre TTS error: %s", err_msg)
                        # Yield error detail in terminal chunk so caller can handle gracefully
                        yield TimbreAudioChunk(
                            data=b"",
                            is_last=True,
                            chunk_index=expected_chunk_index,
                            detail=data,
                        )
                        break
        except websockets.exceptions.ConnectionClosed:
            self._closed = True

    async def interrupt(self) -> None:
        """Cancel synthesis stream cleanly upon user interruption / barge-in.

        Supported operation: closes the active websocket connection without
        sending any undocumented provider messages.
        """
        self._interrupted = True
        self._closed = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
