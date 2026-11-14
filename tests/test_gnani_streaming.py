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
    """Mock websockets connection for testing streaming adapters without network."""
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
    client_25 = PrismaStreamingClient(model="prisma-v2.5", api_key="secret-key")
    assert client_25.model == "prisma-v2.5"
    client_30 = PrismaStreamingClient(model="prisma-v3.0", api_key="secret-key")
    assert client_30.model == "prisma-v3.0"

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
    assert headers["X-API-Key-ID"] == api_key
    assert len([name for name in headers if name.lower() == "x-api-key-id"]) == 1
    assert headers["language_code"] == "en-IN"
    assert headers["model"] == "prisma-v2.5"
    assert headers["format"] == "transcribe"
    assert headers["x-sample-rate"] == "16000"

    # Verify cleanup
    assert mock_ws.closed is True


@pytest.mark.asyncio
async def test_prisma_frame_packetization(monkeypatch):
    mock_ws = MockWebSocket()

    async def mock_connect(url, **kwargs):
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    async with PrismaStreamingClient(api_key="test-key") as client:
        # Send exactly 2048 bytes (packetized into 2 x 1024-byte frames)
        audio_2048 = b"\x01" * 2048
        await client.send_audio(audio_2048)

        assert len(mock_ws.sent_messages) == 2
        assert mock_ws.sent_messages[0] == b"\x01" * PCM_FRAME_BYTES
        assert mock_ws.sent_messages[1] == b"\x01" * PCM_FRAME_BYTES
        assert len(mock_ws.sent_messages[0]) == 1024
        assert len(mock_ws.sent_messages[1]) == 1024

        # Commit sends {"type": "commit"}
        await client.commit()
        assert len(mock_ws.sent_messages) == 3
        commit_msg = json.loads(mock_ws.sent_messages[2])
        assert commit_msg == {"type": "commit"}


@pytest.mark.asyncio
async def test_prisma_event_handling_and_model_verification(monkeypatch, caplog):
    server_events = [
        json.dumps({"type": "connected", "model": "prisma-v3.0"}),
        json.dumps({"type": "speech_start"}),
        json.dumps({"type": "transcript", "text": "Hello world", "is_final": True, "language_code": "en-IN"}),
        json.dumps({"type": "close"}),
    ]
    mock_ws = MockWebSocket(incoming_messages=server_events)

    async def mock_connect(url, **kwargs):
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    with caplog.at_level(logging.WARNING):
        async with PrismaStreamingClient(model="prisma-v2.5", api_key="test-key") as client:
            events = []
            async for evt in client.events():
                events.append(evt)

    assert len(events) == 4
    assert events[0].event == "connected"
    assert events[1].event == "speech_start"
    assert events[2].transcript == "Hello world"
    assert events[2].is_final is True
    assert events[3].event == "close"

    # Verify model mismatch warning
    assert "Prisma model mismatch: requested prisma-v2.5, got prisma-v3.0" in caplog.text


@pytest.mark.asyncio
async def test_timbre_streaming_and_audio_decode(monkeypatch):
    raw_audio_1 = b"\x02" * 500
    b64_chunk_1 = base64.b64encode(raw_audio_1).decode("ascii")
    raw_audio_2 = b"\x03" * 500
    b64_chunk_2 = base64.b64encode(raw_audio_2).decode("ascii")

    server_events = [
        json.dumps({"type": "audio", "audio": b64_chunk_1}),
        json.dumps({"type": "audio", "audio": b64_chunk_2}),
        json.dumps({"type": "complete", "duration_ms": 1200}),
    ]

    mock_ws = MockWebSocket(incoming_messages=server_events)
    connect_calls = []

    async def mock_connect(url, **kwargs):
        connect_calls.append({"url": url, "kwargs": kwargs})
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    api_key = "secret-timbre-key-987"
    async with TimbreStreamingClient(language="te-IN", voice="Suhana", api_key=api_key) as client:
        chunks = []
        async for chunk in client.synthesize("నమస్కారం"):
            chunks.append(chunk)

    assert len(connect_calls) == 1
    assert connect_calls[0]["url"] == TIMBRE_WS_URL
    assert connect_calls[0]["kwargs"]["additional_headers"]["X-API-Key-ID"] == api_key

    # Check synthesis request
    assert len(mock_ws.sent_messages) == 1
    req = json.loads(mock_ws.sent_messages[0])
    assert req["text"] == "నమస్కారం"
    assert req["voice"] == "Suhana"
    assert req["language"] == "te-IN"
    assert req["model"] == "timbre-v2.5"
    assert api_key not in mock_ws.sent_messages[0]

    # Verify decoded chunks
    assert len(chunks) == 3
    assert chunks[0].data == raw_audio_1
    assert chunks[0].is_last is False
    assert chunks[1].data == raw_audio_2
    assert chunks[1].is_last is False
    assert chunks[2].data == b""
    assert chunks[2].is_last is True

    assert mock_ws.closed is True


@pytest.mark.asyncio
async def test_timbre_interruption(monkeypatch):
    raw_audio = b"\x04" * 100
    b64_audio = base64.b64encode(raw_audio).decode("ascii")
    mock_ws = MockWebSocket(incoming_messages=[
        json.dumps({"type": "audio", "audio": b64_audio}),
        json.dumps({"type": "audio", "audio": b64_audio}),
    ])

    async def mock_connect(url, **kwargs):
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    async with TimbreStreamingClient(api_key="test-key") as client:
        # Pull first chunk
        gen = client.synthesize("First sentence")
        chunk1 = await anext(gen)
        assert chunk1.data == raw_audio

        # Candidate barges in: client.interrupt() cancels without sending undocumented messages
        await client.interrupt()
        assert client._interrupted is True
        assert client._closed is True
        # Verify no undocumented message was sent over WS
        assert len(mock_ws.sent_messages) == 1  # Only the original synthesis request was sent
        assert mock_ws.closed is True


@pytest.mark.asyncio
async def test_timbre_nested_data_audio_format(monkeypatch):
    raw_audio_1 = b"\x05" * 200
    b64_1 = base64.b64encode(raw_audio_1).decode("ascii")
    raw_audio_2 = b"\x06" * 200
    b64_2 = base64.b64encode(raw_audio_2).decode("ascii")

    server_events = [
        json.dumps({
            "type": "audio",
            "data": {
                "chunk_index": 0,
                "audio": b64_1,
                "is_final": False,
            }
        }),
        json.dumps({
            "type": "audio",
            "data": {
                "chunk_index": 1,
                "audio": b64_2,
                "is_final": True,
            }
        }),
    ]

    mock_ws = MockWebSocket(incoming_messages=server_events)
    async def mock_connect(*args, **kwargs):
        return mock_ws
    monkeypatch.setattr("websockets.connect", mock_connect)

    async with TimbreStreamingClient(api_key="test-key") as client:
        chunks = []
        async for chunk in client.synthesize("Testing nested format"):
            chunks.append(chunk)

    assert len(chunks) == 3
    assert chunks[0].data == raw_audio_1
    assert chunks[0].chunk_index == 0
    assert chunks[0].is_last is False

    assert chunks[1].data == raw_audio_2
    assert chunks[1].chunk_index == 1
    assert chunks[1].is_last is False

    # Terminal chunk generated from is_final=True
    assert chunks[2].data == b""
    assert chunks[2].is_last is True


@pytest.mark.asyncio
async def test_prisma_vad_and_rate_headers(monkeypatch):
    mock_ws = MockWebSocket()
    captured_headers = {}

    async def mock_connect(url, additional_headers=None, **kwargs):
        nonlocal captured_headers
        captured_headers = additional_headers or {}
        return mock_ws

    monkeypatch.setattr("websockets.connect", mock_connect)

    async with PrismaStreamingClient(
        language_code="hi-IN",
        model="prisma-v3.0",
        api_key="test-key-hi",
        silence_timeout_s=2.0,
        sample_rate=16000,
    ) as client:
        pass

    assert captured_headers["x-sample-rate"] == "16000"
    assert captured_headers["x-min-silence-ms"] == "2000"
    assert captured_headers["x-vad-threshold"] == "0.5"
    assert captured_headers["x-min-speech-ms"] == "250"
    assert captured_headers["format"] == "codemix"
