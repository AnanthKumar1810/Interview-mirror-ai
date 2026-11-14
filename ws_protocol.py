"""WebSocket protocol definitions for hands-free realtime voice pipeline.

Version 1.0 JSON control messages + raw PCM binary audio frames.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

PROTOCOL_VERSION = "1.0"

# Bounded constraints
MAX_QUEUE_DEPTH = 256
MAX_SESSION_DURATION_S = 600
SEQUENCE_NUMBER_MAX = 2**32
PCM_FRAME_BYTES = 1024  # 512 samples × 2 bytes (16-bit PCM @ 16 kHz)


class ProtocolError(ValueError):
    """Base protocol violation error."""


class ProtocolVersionError(ProtocolError):
    """Raised when protocol_version does not match PROTOCOL_VERSION."""


def check_protocol_version(version: str) -> bool:
    return version == PROTOCOL_VERSION


def validate_protocol_version(version: str) -> None:
    if version != PROTOCOL_VERSION:
        raise ProtocolVersionError(
            f"Protocol version mismatch: expected {PROTOCOL_VERSION}, got {version}"
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


def next_sequence_number(current: int) -> int:
    return (current + 1) % SEQUENCE_NUMBER_MAX


_next_seq = next_sequence_number


@dataclass
class ProtocolMessage:
    """Base for JSON control messages."""
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


@dataclass
class SessionStart(ProtocolMessage):
    type: str = "session_start"
    track: str = "agentic"
    language: str = "en-IN"
    consent_given: bool = False
    stt_model: str = "prisma-v2.5"
    session_id: Optional[str] = None
    token: Optional[str] = None
    endpointing_policy: str = "fixed"  # fixed, two_stage, adaptive
    resume_text: Optional[str] = None
    github_repo: Optional[str] = None
    target_questions: int = 3
    role: str = "Software Engineer"


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
    event: str = ""
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
    is_turn_final: bool = False
    source: str = "gnani_prisma"
    provider_latency_ms: float = 0.0


@dataclass
class TurnStateMessage(ProtocolMessage):
    type: str = "turn_state"
    state: str = ""  # Interviewer speaking, Listening, Processing answer, Complete
    raw_state: str = ""  # internal state machine enum value
    question: str = ""
    question_number: int = 0
    feedback: Optional[dict] = None
    session_id: str = ""


@dataclass
class BargeInMessage(ProtocolMessage):
    type: str = "barge_in"
    generation_id: int = 0
    stop_delay_ms: float = 0.0


@dataclass
class RepromptMessage(ProtocolMessage):
    type: str = "reprompt"
    text: str = ""


@dataclass
class EndInterviewMessage(ProtocolMessage):
    type: str = "end_interview"
    session_id: str = ""


@dataclass
class TTSAudioMeta(ProtocolMessage):
    type: str = "tts_audio_meta"
    voice: str = ""
    language: str = ""
    duration_ms: float = 0.0
    size_bytes: int = 0
    generation_id: int = 0
    sample_rate: int = 24000
    encoding: str = "pcm_s16le"


@dataclass
class TTSAudioComplete(ProtocolMessage):
    type: str = "tts_complete"
    generation_id: int = 0


@dataclass
class PlaybackStartMessage(ProtocolMessage):
    type: str = "playback_start"
    generation_id: int = 0
    client_timestamp_ms: int = 0


@dataclass
class PlaybackStopMessage(ProtocolMessage):
    type: str = "playback_stop"
    generation_id: int = 0
    client_timestamp_ms: int = 0


@dataclass
class MetricsMessage(ProtocolMessage):
    type: str = "metrics"
    data: dict = field(default_factory=dict)


@dataclass
class PingMessage(ProtocolMessage):
    type: str = "ping"


@dataclass
class SessionResume(ProtocolMessage):
    type: str = "session_resume"
    session_id: str = ""
    token: Optional[str] = None


@dataclass
class IntentMessage(ProtocolMessage):
    type: str = "intent"
    intent: str = ""  # clarification, repeat, uncertainty, skip, answer
    action: str = ""
    note: str = ""


@dataclass
class PongMessage(ProtocolMessage):
    type: str = "pong"


_TYPE_REGISTRY: dict[str, type] = {
    "session_start": SessionStart,
    "session_resume": SessionResume,
    "session_ack": SessionAck,
    "provider_event": ProviderEvent,
    "error": ErrorMessage,
    "transcript": TranscriptMessage,
    "turn_state": TurnStateMessage,
    "intent": IntentMessage,
    "barge_in": BargeInMessage,
    "reprompt": RepromptMessage,
    "end_interview": EndInterviewMessage,
    "tts_audio_meta": TTSAudioMeta,
    "tts_complete": TTSAudioComplete,
    "playback_start": PlaybackStartMessage,
    "playback_stop": PlaybackStopMessage,
    "metrics": MetricsMessage,
    "ping": PingMessage,
    "pong": PongMessage,
}


def parse_message(raw: str | bytes | dict, *, validate_version: bool = False) -> ProtocolMessage:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return ProtocolMessage.from_json(raw, validate_version=validate_version)


def is_pcm_frame(data: bytes) -> bool:
    return isinstance(data, bytes) and len(data) == PCM_FRAME_BYTES
