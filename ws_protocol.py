"""WebSocket protocol definitions for browser ↔ FastAPI realtime voice pipeline.

Protocol version 1.0 — JSON control messages and raw PCM binary frames.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

PROTOCOL_VERSION = "1.0"

# Bounds
MAX_QUEUE_DEPTH = 256
MAX_SESSION_DURATION_S = 600
SEQUENCE_NUMBER_MAX = 2**32  # overflow wrap-around point
PCM_FRAME_BYTES = 1024       # 512 samples × 2 bytes (16-bit PCM)


class ProtocolError(ValueError):
    """Base error for protocol violations."""


class ProtocolVersionError(ProtocolError):
    """Raised when message protocol_version does not match PROTOCOL_VERSION."""


def check_protocol_version(version: str) -> bool:
    """Return True if version matches PROTOCOL_VERSION, False otherwise."""
    return version == PROTOCOL_VERSION


def validate_protocol_version(version: str) -> None:
    """Raise ProtocolVersionError if version does not match PROTOCOL_VERSION."""
    if version != PROTOCOL_VERSION:
        raise ProtocolVersionError(
            f"Protocol version mismatch: expected {PROTOCOL_VERSION}, got {version}"
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


def next_sequence_number(current: int) -> int:
    """Increment sequence number with overflow wrapping at 2^32."""
    return (current + 1) % SEQUENCE_NUMBER_MAX


_next_seq = next_sequence_number


# ---------------------------------------------------------------------------
# Base message
# ---------------------------------------------------------------------------

@dataclass
class ProtocolMessage:
    """Base for all JSON control messages."""
    type: str
    protocol_version: str = field(default=PROTOCOL_VERSION)
    sequence_number: int = 0
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_ms: int = field(default_factory=_now_ms)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | dict, *, validate_version: bool = False) -> "ProtocolMessage":
        data = raw if isinstance(raw, dict) else json.loads(raw)
        if not isinstance(data, dict):
            raise ProtocolError("Message must be a JSON object")
        msg_type = data.get("type", "")
        if cls is ProtocolMessage:
            if not msg_type or msg_type not in _TYPE_REGISTRY:
                raise ProtocolError(f"Unknown or missing message type: {msg_type}")
            target_cls = _TYPE_REGISTRY[msg_type]
        else:
            target_cls = cls
        if validate_version:
            version = data.get("protocol_version", PROTOCOL_VERSION)
            validate_protocol_version(version)
        known_fields = {f.name for f in target_cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return target_cls(**filtered)


# ---------------------------------------------------------------------------
# Concrete message types
# ---------------------------------------------------------------------------

@dataclass
class SessionStart(ProtocolMessage):
    type: str = "session_start"
    track: str = "agentic"
    language: str = "en-IN"
    consent_given: bool = False
    stt_model: str = "prisma-v2.5"


@dataclass
class SessionAck(ProtocolMessage):
    type: str = "session_ack"
    session_id: str = ""
    status: str = "ok"
    question: str = ""
    question_number: int = 1
    total_questions: int = 3


@dataclass
class ProviderEvent(ProtocolMessage):
    type: str = "provider_event"
    event: str = ""          # connected, speech_start, processing, transcript-final, error, close
    detail: dict = field(default_factory=dict)


@dataclass
class ErrorMessage(ProtocolMessage):
    type: str = "error"
    code: str = ""
    message: str = ""
    recoverable: bool = True


@dataclass
class TranscriptMessage(ProtocolMessage):
    type: str = "transcript"
    text: str = ""
    is_final: bool = False
    source: str = "gnani_prisma"
    provider_latency_ms: float = 0.0


@dataclass
class TurnStateMessage(ProtocolMessage):
    type: str = "turn_state"
    state: str = ""           # matches InterviewState enum values
    question: str = ""
    question_number: int = 0
    feedback: Optional[dict] = None


@dataclass
class TTSAudioMeta(ProtocolMessage):
    type: str = "tts_audio_meta"
    voice: str = ""
    language: str = ""
    duration_ms: float = 0.0
    size_bytes: int = 0


@dataclass
class MetricsMessage(ProtocolMessage):
    type: str = "metrics"
    data: dict = field(default_factory=dict)


@dataclass
class PingMessage(ProtocolMessage):
    type: str = "ping"


@dataclass
class PongMessage(ProtocolMessage):
    type: str = "pong"


@dataclass
class EndAudioMessage(ProtocolMessage):
    type: str = "end_audio"


# ---------------------------------------------------------------------------
# Registry for dispatch
# ---------------------------------------------------------------------------

_TYPE_REGISTRY: dict[str, type] = {
    "session_start": SessionStart,
    "session_ack": SessionAck,
    "provider_event": ProviderEvent,
    "error": ErrorMessage,
    "transcript": TranscriptMessage,
    "turn_state": TurnStateMessage,
    "tts_audio_meta": TTSAudioMeta,
    "metrics": MetricsMessage,
    "ping": PingMessage,
    "pong": PongMessage,
    "end_audio": EndAudioMessage,
}


def parse_message(raw: str | bytes | dict, *, validate_version: bool = False) -> ProtocolMessage:
    """Parse an incoming JSON control message."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return ProtocolMessage.from_json(raw, validate_version=validate_version)


def is_pcm_frame(data: bytes) -> bool:
    """Check if incoming binary data is a valid PCM audio frame."""
    return isinstance(data, bytes) and len(data) == PCM_FRAME_BYTES
