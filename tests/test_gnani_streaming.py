import asyncio
import base64
import json
import logging
import pytest
from gnani_streaming import (
    PRISMA_WS_URL,
    TIMBRE_WS_URL,
    PCM_FRAME_BYTES,
    PrismaStreamingClient,
    TimbreStreamingClient,
    PrismaEvent,
    TimbreAudioChunk,
)


class MockWebSocket:
    """Mock websockets connection for testing streaming adapters without real network."""
    def __init__(self, incoming_messages=None):
        self.sent_messages = []
        self.closed = False
        self._incoming = list(incoming_messages or [])
        self._recv_index = 0

    async def send(self, data):
        self.sent_messages.append(data)

    async def close(self, code=1000, reason=""):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._recv_index < len(self._incoming):
            msg = self._incoming[self._recv_index]
            self._recv_index += 1
            return msg
        raise StopAsyncIteration


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc1:
        PrismaStreamingClient(language_code="en-IN", api_key="")
    assert "GNANI_API_KEY is required" in str(exc1.value)

    with pytest.raises(RuntimeError) as exc2:
        TimbreStreamingClient(language="en-IN", api_key="")
    assert "GNANI_API_KEY is required" in str(exc2.value)


def test_prisma_model_validation():
    # Supported models
    client_25 = PrismaStreamingClient(model="prisma-v2.5", api_key="secret-key")
    assert client_25.model == "prisma-v2.5"
    client_30 = PrismaStreamingClient(model="prisma-v3.0", api_key="secret-key")
    assert client_30.model == "prisma-v3.0"

    # Unsupported model
    with pytest.raises(ValueError) as exc:
        PrismaStreamingClient(model="whisper-large", api_key="secret-key")
    assert "Unsupported Prisma model" in str(exc.value)


@pytest.mark.asyncio
async def test_prisma_client_config_and_api_key_in_headers(monkeypatch):
    mock_ws = MockWebSocket()
    connect_calls = []

    async def mock_connect(url, **kwargs):
        connect_calls.append({"url": url, "kwargs": kwargs})
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    api_key = "super-secret-gnani-key-12345"
    async with PrismaStreamingClient(
        language_code="en-IN",
        model="prisma-v2.5",
        api_key=api_key,
        silence_timeout_s=1.5,
        sample_rate=16000,
    ) as client:
        assert client._ws is mock_ws

    # Check connection parameters
    assert len(connect_calls) == 1
    call = connect_calls[0]
    assert call["url"] == PRISMA_WS_URL
    headers = call["kwargs"]["additional_headers"]
    assert headers["x-api-key-id"] == api_key

    # Gnani accepts configuration in handshake headers, not a JSON frame.
    assert mock_ws.sent_messages == []
    assert headers["language_code"] == "en-IN"
    assert headers["model"] == "prisma-v2.5"
    assert headers["format"] == "transcribe"
    assert headers["x-sample-rate"] == "16000"
    assert headers["x-min-silence-ms"] == "1500"

    # VERIFY: API key must NOT be leaked into message payloads
    assert all(api_key not in str(msg) for msg in mock_ws.sent_messages)

    # Verify cleanup
    assert mock_ws.closed is True


@pytest.mark.asyncio
async def test_prisma_frame_packetization(monkeypatch):
    mock_ws = MockWebSocket()

    async def mock_connect(url, **kwargs):
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    async with PrismaStreamingClient(api_key="test-key") as client:
        assert len(mock_ws.sent_messages) == 0

        # Send exactly 2048 bytes (should be packetized into 2 x 1024 byte chunks)
        audio_2048 = b"\x01" * 2048
        await client.send_audio(audio_2048)

        assert len(mock_ws.sent_messages) == 2
        assert mock_ws.sent_messages[0] == b"\x01" * PCM_FRAME_BYTES
        assert mock_ws.sent_messages[1] == b"\x01" * PCM_FRAME_BYTES
        assert len(mock_ws.sent_messages[0]) == 1024
        assert len(mock_ws.sent_messages[1]) == 1024

        # Send EOF
        await client.send_eof()
        assert len(mock_ws.sent_messages) == 3
        eof_msg = json.loads(mock_ws.sent_messages[2])
        assert eof_msg == {"type": "commit"}


@pytest.mark.asyncio
async def test_prisma_event_handling_and_model_verification(monkeypatch, caplog):
    server_events = [
        json.dumps({"type": "connected", "model": "prisma-v3.0"}),
        json.dumps({"type": "speech_start"}),
        json.dumps({"type": "transcript", "text": "Hello world", "is_final": True, "detected_language_code": "en-IN"}),
        json.dumps({"type": "close"}),
    ]
    mock_ws = MockWebSocket(incoming_messages=server_events)

    async def mock_connect(url, **kwargs):
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    # We requested prisma-v2.5, server returned prisma-v3.0 -> should trigger warning log
    with caplog.at_level(logging.WARNING):
        async with PrismaStreamingClient(model="prisma-v2.5", api_key="test-key") as client:
            events = []
            async for evt in client.events():
                events.append(evt)

    assert len(events) == 4
    assert events[0].event == "connected"
    assert events[1].event == "speech_start"
    assert events[2].event == "transcript"
    assert events[2].transcript == "Hello world"
    assert events[2].is_final is True
    assert events[3].event == "close"

    # Verify model mismatch warning
    assert "Prisma model mismatch: requested prisma-v2.5, got prisma-v3.0" in caplog.text


@pytest.mark.asyncio
async def test_timbre_streaming_and_audio_decode(monkeypatch):
    pcm_chunk_1 = b"\x02" * 500
    pcm_chunk_2 = b"\x03" * 500
    done_event = json.dumps({"type": "complete", "duration_ms": 1200})

    mock_ws = MockWebSocket(incoming_messages=[
        json.dumps({"type": "audio", "data": {"audio": base64.b64encode(pcm_chunk_1).decode()}}),
        json.dumps({"type": "audio", "data": {"audio": base64.b64encode(pcm_chunk_2).decode()}}),
        done_event,
    ])
    connect_calls = []

    async def mock_connect(url, **kwargs):
        connect_calls.append({"url": url, "kwargs": kwargs})
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    api_key = "secret-timbre-key-987"
    async with TimbreStreamingClient(language="te-IN", voice="Aarav", api_key=api_key) as client:
        chunks = []
        async for chunk in client.synthesize("నమస్కారం"):
            chunks.append(chunk)

    # Verify headers and URL
    assert len(connect_calls) == 1
    assert connect_calls[0]["url"] == TIMBRE_WS_URL
    assert connect_calls[0]["kwargs"]["additional_headers"]["x-api-key-id"] == api_key

    # Verify synthesize request sent
    assert len(mock_ws.sent_messages) == 1
    req = json.loads(mock_ws.sent_messages[0])
    assert req["text"] == "నమస్కారం"
    assert req["voice"] == "Aarav"
    assert req["language"] == "te-IN"
    assert req["model"] == "timbre-v2.5"
    assert req["audio_config"] == {"container": "raw", "sample_rate": 16000}

    # VERIFY: API key must NEVER be in message body
    assert api_key not in mock_ws.sent_messages[0]

    # Verify received chunks
    assert len(chunks) == 3
    assert chunks[0].data == pcm_chunk_1
    assert chunks[0].is_last is False
    assert chunks[1].data == pcm_chunk_2
    assert chunks[1].is_last is False
    assert chunks[2].data == b""
    assert chunks[2].is_last is True
    assert chunks[2].detail["duration_ms"] == 1200

    # Verify cleanup
    assert mock_ws.closed is True


@pytest.mark.asyncio
async def test_timbre_interruption(monkeypatch):
    pcm_chunk = b"\x04" * 100
    mock_ws = MockWebSocket(incoming_messages=[
        json.dumps({"type": "audio", "data": {"audio": base64.b64encode(pcm_chunk).decode()}}),
    ])

    async def mock_connect(url, **kwargs):
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    async with TimbreStreamingClient(api_key="test-key") as client:
        await client.interrupt()
        assert client._interrupted is True

        assert mock_ws.closed is True

        # synthesize should terminate early if interrupted
        chunks = []
        # Calling synthesize resets interrupted flag at the start,
        # but let's test interrupting during playback
        gen = client.synthesize("Some phrase")
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
