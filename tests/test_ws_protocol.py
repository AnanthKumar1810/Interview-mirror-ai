import json
import pytest
from ws_protocol import (
    PROTOCOL_VERSION,
    SEQUENCE_NUMBER_MAX,
    PCM_FRAME_BYTES,
    ProtocolError,
    ProtocolVersionError,
    check_protocol_version,
    validate_protocol_version,
    next_sequence_number,
    ProtocolMessage,
    SessionStart,
    SessionAck,
    ProviderEvent,
    ErrorMessage,
    TranscriptMessage,
    TurnStateMessage,
    BargeInMessage,
    RepromptMessage,
    EndInterviewMessage,
    TTSAudioMeta,
    MetricsMessage,
    PingMessage,
    PongMessage,
    parse_message,
    is_pcm_frame,
)


def test_protocol_version_validation():
    assert check_protocol_version("1.0") is True
    assert check_protocol_version("2.0") is False
    assert check_protocol_version("") is False

    validate_protocol_version("1.0")

    with pytest.raises(ProtocolVersionError) as exc_info:
        validate_protocol_version("0.9")
    assert "Protocol version mismatch" in str(exc_info.value)

    with pytest.raises(ProtocolVersionError):
        validate_protocol_version("2.0")


def test_sequence_number_overflow():
    assert next_sequence_number(0) == 1
    assert next_sequence_number(100) == 101
    assert next_sequence_number(SEQUENCE_NUMBER_MAX - 2) == SEQUENCE_NUMBER_MAX - 1
    # Wrap-around at 2^32
    assert next_sequence_number(SEQUENCE_NUMBER_MAX - 1) == 0
    assert next_sequence_number(SEQUENCE_NUMBER_MAX) == 1


def test_all_message_types_serialization_and_deserialization():
    messages = [
        SessionStart(track="agentic", language="te-IN", consent_given=True, stt_model="prisma-v3.0"),
        SessionAck(session_id="test-session-123", status="ok", question="Tell me about your project", question_number=1, total_questions=3),
        ProviderEvent(event="speech_start", detail={"confidence": 0.95}),
        ErrorMessage(code="vad_timeout", message="Silence detected", recoverable=True),
        TranscriptMessage(text="I built an agent with Python", is_final=True, source="gnani_prisma", provider_latency_ms=120.5),
        TurnStateMessage(state="asking", question="How did you test it?", question_number=2, feedback={"score": 8}),
        TTSAudioMeta(voice="Pranav", language="en-IN", duration_ms=2500.0, size_bytes=80000),
        MetricsMessage(data={"e2e_p50": 340.0, "e2e_p95": 620.0}),
        BargeInMessage(generation_id=2),
        RepromptMessage(text="Whenever you're ready..."),
        EndInterviewMessage(session_id="test-session-123"),
        PingMessage(),
        PongMessage(),
    ]

    for msg in messages:
        # Check to_json() produces valid JSON
        serialized = msg.to_json()
        assert isinstance(serialized, str)
        data = json.loads(serialized)
        assert data["type"] == msg.type
        assert data["protocol_version"] == PROTOCOL_VERSION
        assert "turn_id" in data
        assert "timestamp_ms" in data

        # Check parse_message round-trip
        parsed = parse_message(serialized)
        assert isinstance(parsed, type(msg))
        assert parsed.type == msg.type

        # Verify message-specific fields round-trip
        if isinstance(msg, SessionStart):
            assert parsed.track == "agentic"
            assert parsed.language == "te-IN"
            assert parsed.consent_given is True
            assert parsed.stt_model == "prisma-v3.0"
        elif isinstance(msg, SessionAck):
            assert parsed.session_id == "test-session-123"
            assert parsed.question == "Tell me about your project"
            assert parsed.question_number == 1
        elif isinstance(msg, ProviderEvent):
            assert parsed.event == "speech_start"
            assert parsed.detail == {"confidence": 0.95}
        elif isinstance(msg, ErrorMessage):
            assert parsed.code == "vad_timeout"
            assert parsed.message == "Silence detected"
            assert parsed.recoverable is True
        elif isinstance(msg, TranscriptMessage):
            assert parsed.text == "I built an agent with Python"
            assert parsed.is_final is True
            assert parsed.provider_latency_ms == 120.5
        elif isinstance(msg, TurnStateMessage):
            assert parsed.state == "asking"
            assert parsed.question == "How did you test it?"
            assert parsed.feedback == {"score": 8}
        elif isinstance(msg, TTSAudioMeta):
            assert parsed.voice == "Pranav"
            assert parsed.duration_ms == 2500.0
            assert parsed.size_bytes == 80000
        elif isinstance(msg, MetricsMessage):
            assert parsed.data == {"e2e_p50": 340.0, "e2e_p95": 620.0}


def test_parse_message_from_dict_and_bytes():
    raw_dict = {"type": "ping", "sequence_number": 5}
    msg_from_dict = parse_message(raw_dict)
    assert isinstance(msg_from_dict, PingMessage)
    assert msg_from_dict.sequence_number == 5

    raw_bytes = json.dumps({"type": "pong", "sequence_number": 6}).encode("utf-8")
    msg_from_bytes = parse_message(raw_bytes)
    assert isinstance(msg_from_bytes, PongMessage)
    assert msg_from_bytes.sequence_number == 6


def test_parse_message_version_validation():
    valid_payload = json.dumps({"type": "ping", "protocol_version": "1.0"})
    invalid_payload = json.dumps({"type": "ping", "protocol_version": "9.9"})

    # validate_version=True checks version
    assert parse_message(valid_payload, validate_version=True).type == "ping"
    with pytest.raises(ProtocolVersionError):
        parse_message(invalid_payload, validate_version=True)

    # validate_version=False allows mismatched version through
    msg = parse_message(invalid_payload, validate_version=False)
    assert msg.protocol_version == "9.9"


def test_invalid_message_rejection():
    # Not JSON
    with pytest.raises(Exception):
        parse_message("not a json string")

    # JSON not an object
    with pytest.raises(ProtocolError):
        parse_message("42")
    with pytest.raises(ProtocolError):
        parse_message('["a", "b"]')

    # Missing or empty type
    with pytest.raises(ProtocolError):
        parse_message("{}")
    with pytest.raises(ProtocolError):
        parse_message('{"type": ""}')

    # Unknown message type
    with pytest.raises(ProtocolError) as exc_info:
        parse_message('{"type": "unregistered_custom_type"}')
    assert "Unknown or missing message type" in str(exc_info.value)


def test_is_pcm_frame():
    assert is_pcm_frame(bytes(1024)) is True
    assert is_pcm_frame(bytes(512)) is False
    assert is_pcm_frame(bytes(1025)) is False
    assert is_pcm_frame(b"") is False
    assert is_pcm_frame("not bytes") is False
    assert is_pcm_frame(None) is False
