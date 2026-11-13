"""Gnani streaming WebSocket adapters — Prisma STT and Timbre TTS.

Both clients are async context managers with proper cancellation.
Never leak the API key to the browser.
Uses the ``websockets`` library.
"""
from __future__ import annotations

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

# ---------------------------------------------------------------------------
# Prisma streaming STT
# ---------------------------------------------------------------------------

PRISMA_WS_URL = "wss://api.vachana.ai/stt/v3/stream"

# Supported Prisma model versions
_PRISMA_MODELS = {"prisma-v2.5", "prisma-v3.0"}

PCM_FRAME_BYTES = 1024  # 512 samples × 2 bytes


@dataclass
class PrismaEvent:
    """Parsed event from the Prisma STT WebSocket."""
    event: str            # connected, speech_start, processing, transcript-final, error, close
    transcript: str = ""
    is_final: bool = False
    language_code: str = ""
    detail: dict = field(default_factory=dict)
    latency_ms: float = 0.0


class PrismaStreamingClient:
    """Realtime Prisma STT over WebSocket.

    Usage::

        async with PrismaStreamingClient(language_code="en-IN") as client:
            await client.send_audio(pcm_chunk)
            async for event in client.events():
                ...
    """

    def __init__(
        self,
        language_code: str = "en-IN",
        model: str = "prisma-v2.5",
        *,
        api_key: Optional[str] = None,
        silence_timeout_s: float = 0.7,
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
        self._send_ts: float = 0.0  # for latency tracking
        self._frames_sent: int = 0

    async def __aenter__(self) -> "PrismaStreamingClient":
        headers = {
            "x-api-key-id": self._api_key,
            "language_code": self.language_code,
            "model": self.model,
            "x-sample-rate": str(self.sample_rate),
            "format": "codemix" if self.model == "prisma-v3.0" else "transcribe",
            "x-min-silence-ms": str(round(self.silence_timeout_s * 1000)),
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
        if len(pcm_data) % PCM_FRAME_BYTES:
            raise ValueError("Prisma requires complete 1024-byte PCM frames")
        # Send in frame-sized chunks
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

    async def send_eof(self) -> None:
        """Signal end-of-audio to the provider."""
        if self._ws is None or self._closed:
            return
        try:
            await self._ws.send(json.dumps({"type": "commit"}))
        except websockets.exceptions.ConnectionClosed:
            self._closed = True

    async def events(self) -> AsyncIterator[PrismaEvent]:
        """Yield parsed events from the Prisma stream."""
        if self._ws is None:
            return
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue  # unexpected binary; skip
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type", "unknown")
                now = time.monotonic()
                latency = (now - self._send_ts) * 1000 if self._send_ts > 0 else 0.0

                evt = PrismaEvent(
                    event=event_type,
                    transcript=data.get("text", ""),
                    is_final=event_type == "transcript" and data.get("is_final") is True,
                    language_code=data.get("detected_language_code", self.language_code),
                    detail=data,
                    latency_ms=round(latency, 2),
                )

                # Verify model/language match on connected event
                if event_type == "connected":
                    server_model = data.get("model", "")
                    if server_model and server_model != self.model:
                        logger.warning(
                            "Prisma model mismatch: requested %s, got %s",
                            self.model, server_model,
                        )

                yield evt

                if event_type in ("error", "close"):
                    break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._closed = True


# ---------------------------------------------------------------------------
# Timbre streaming TTS
# ---------------------------------------------------------------------------

TIMBRE_WS_URL = "wss://api.vachana.ai/api/v1/tts"


@dataclass
class TimbreAudioChunk:
    """A decoded audio chunk from Timbre TTS."""
    data: bytes
    is_last: bool = False
    detail: dict = field(default_factory=dict)


class TimbreStreamingClient:
    """Realtime Timbre TTS over WebSocket.

    Usage::

        async with TimbreStreamingClient(language="en-IN") as client:
            async for chunk in client.synthesize("Hello world"):
                # chunk.data contains PCM audio bytes
                ...
    """

    def __init__(
        self,
        language: str = "en-IN",
        *,
        api_key: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> None:
        self._api_key = (api_key or os.getenv("GNANI_API_KEY", "")).strip()
        if not self._api_key:
            raise RuntimeError("GNANI_API_KEY is required for Timbre streaming.")
        self.language = language
        self.voice = voice or VOICE.get(language, "Pranav")
        self._ws: Optional[Any] = None
        self._closed = False
        self._interrupted = False

    async def __aenter__(self) -> "TimbreStreamingClient":
        headers = {"x-api-key-id": self._api_key}
        try:
            self._ws = await websockets.connect(
                TIMBRE_WS_URL,
                additional_headers=headers,
                max_size=2**22,  # TTS audio chunks can be larger
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
        """Send a phrase and yield audio chunks as they arrive."""
        if self._ws is None or self._closed:
            return
        self._interrupted = False

        request = {
            "text": text.strip(),
            "voice": self.voice,
            "language": self.language,
            "model": "timbre-v2.5",
            "speed": 1.0,
            "audio_config": {"container": "raw", "sample_rate": 16000},
        }
        try:
            await self._ws.send(json.dumps(request))
        except websockets.exceptions.ConnectionClosed:
            self._closed = True
            return

        try:
            async for raw in self._ws:
                if self._interrupted:
                    break
                if not isinstance(raw, bytes):
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    event = data.get("type", "")
                    if event == "audio":
                        payload = data.get("data", {})
                        encoded = payload.get("audio", "")
                        if encoded:
                            yield TimbreAudioChunk(data=base64.b64decode(encoded, validate=True), detail=payload)
                    elif event == "complete":
                        yield TimbreAudioChunk(data=b"", is_last=True, detail=data)
                        break
                    elif event == "error":
                        logger.error("Timbre TTS error: %s", data.get("message", ""))
                        break
        except websockets.exceptions.ConnectionClosed:
            self._closed = True

    async def interrupt(self) -> None:
        """Signal that playback was interrupted (e.g. user started speaking)."""
        self._interrupted = True
        if self._ws is not None and not self._closed:
            try:
                await self._ws.close()
                self._closed = True
            except websockets.exceptions.ConnectionClosed:
                self._closed = True
