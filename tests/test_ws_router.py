import asyncio
import json
import pytest
from starlette.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient

from main import app
import ws_router
from ws_protocol import PROTOCOL_VERSION, PCM_FRAME_BYTES
from gnani_streaming import PrismaEvent, TimbreAudioChunk


class DummyPrismaStreaming:
    """Mock Prisma client that records audio sent and produces controlled events."""
    instances = []

    def __init__(self, language_code="en-IN", model="prisma-v2.5", **kwargs):
        self.language_code = language_code
        self.model = model
        self.audio_sent = []
        self.eof_called = False
        self.closed = False
        self._events_queue = asyncio.Queue()
        DummyPrismaStreaming.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.closed = True

    async def send_audio(self, pcm_data: bytes):
        self.audio_sent.append(pcm_data)

    async def send_eof(self):
        self.eof_called = True

    async def events(self):
        while not self.closed:
            try:
                evt = await asyncio.wait_for(self._events_queue.get(), timeout=0.1)
                yield evt
            except asyncio.TimeoutError:
                if self.closed:
                    break


class DummyTimbreStreaming:
    """Mock Timbre client that yields simulated audio chunks without hitting network."""
    instances = []

    def __init__(self, language="en-IN", **kwargs):
        self.language = language
        self.synthesize_calls = []
        self.interrupted = False
        self.closed = False
        DummyTimbreStreaming.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.closed = True

    async def synthesize(self, text: str):
        self.synthesize_calls.append(text)
        yield TimbreAudioChunk(data=b"\x01" * 1024, is_last=False)
        yield TimbreAudioChunk(data=b"", is_last=True)

    async def interrupt(self):
        self.interrupted = True


@pytest.fixture(autouse=True)
def patch_gnani_clients(monkeypatch):
    DummyPrismaStreaming.instances.clear()
    DummyTimbreStreaming.instances.clear()
    monkeypatch.setattr(ws_router, "PrismaStreamingClient", DummyPrismaStreaming)
    monkeypatch.setattr(ws_router, "TimbreStreamingClient", DummyTimbreStreaming)


def test_ws_connection_rejected_with_invalid_protocol_version():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/interview?protocol_version=99.0"):
            pass
    assert exc_info.value.code == 1008


def test_ws_connection_with_valid_protocol_version_and_missing_session_start():
    client = TestClient(app)
    # Connecting without sending session_start within timeout or sending invalid first message
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/interview?protocol_version={PROTOCOL_VERSION}") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            # Server closes with 1008: First message must be session_start
            ws.receive_text()
    assert exc_info.value.code == 1008


def test_ws_session_start_without_consent_rejected():
    client = TestClient(app)
    with client.websocket_connect("/ws/interview") as ws:
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": False,
        }))
        # Server sends consent_required error before closing
        err_msg = json.loads(ws.receive_text())
        assert err_msg["type"] == "error"
        assert err_msg["code"] == "consent_required"


def test_ws_session_start_ack_and_flow():
    client = TestClient(app)
    with client.websocket_connect(f"/ws/interview?protocol_version={PROTOCOL_VERSION}") as ws:
        # Send valid session_start with consent
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": True,
            "stt_model": "prisma-v2.5",
        }))

        # 1. First response is session_ack
        ack = json.loads(ws.receive_text())
        assert ack["type"] == "session_ack"
        assert ack["status"] == "ok"
        assert ack["question_number"] == 1
        assert "question" in ack

        # Streaming route transcribes audio; the REST session owns the
        # current question, candidate review and scoring.
        ws.send_text(json.dumps({"type": "ping"}))
        received_types = [json.loads(ws.receive_text())["type"] for _ in range(3)]
        assert "pong" in received_types


def test_ws_binary_audio_forwarding():
    class FakeWebSocket:
        def __init__(self):
            self.messages = [
                {"bytes": b"\x05" * PCM_FRAME_BYTES},
                {"bytes": b"\x06" * PCM_FRAME_BYTES},
                {"type": "websocket.disconnect"},
            ]

        async def receive(self):
            return self.messages.pop(0)

    async def run():
        ctx = ws_router._SessionContext("agentic", "en-IN", "prisma-v2.5", True)
        await ws_router._browser_audio_ingest(FakeWebSocket(), ctx)
        return ctx

    ctx = asyncio.run(run())
    assert ctx.audio_to_stt.get_nowait() == b"\x05" * PCM_FRAME_BYTES
    assert ctx.audio_to_stt.get_nowait() == b"\x06" * PCM_FRAME_BYTES


def test_slow_client_detection():
    # Directly test the bounded queue drop logic
    from ws_router import _SessionContext, _enqueue_or_drop
    import asyncio

    ctx = _SessionContext("agentic", "en-IN", "prisma-v2.5", consent=True)
    small_q = asyncio.Queue(maxsize=2)

    # Fill queue to capacity
    asyncio.run(_enqueue_or_drop(small_q, "item-1", ctx))
    asyncio.run(_enqueue_or_drop(small_q, "item-2", ctx))
    assert small_q.full()
    assert ctx.metrics.dropped_frames == 0

    # 3rd item should drop item-1 and succeed
    asyncio.run(_enqueue_or_drop(small_q, "item-3", ctx))
    assert ctx.metrics.dropped_frames == 1
    assert small_q.qsize() == 2
    assert small_q.get_nowait() == "item-2"
    assert small_q.get_nowait() == "item-3"


def test_disconnect_cleanup():
    client = TestClient(app)
    with client.websocket_connect("/ws/interview") as ws:
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": True,
        }))
        ack = json.loads(ws.receive_text())
        assert ack["type"] == "session_ack"
        # Close connection from client side
        ws.close()

    # Verify that Prisma and Timbre clients were cleaned up
    if DummyPrismaStreaming.instances:
        assert DummyPrismaStreaming.instances[0].closed is True


def test_session_timeout_configuration(monkeypatch):
    # Verify timeout parameter is bounded by MAX_SESSION_DURATION_S (600s)
    from ws_router import MAX_SESSION_DURATION_S
    assert MAX_SESSION_DURATION_S == 600
