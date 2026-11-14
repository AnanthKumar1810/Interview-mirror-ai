import asyncio
import json
import pytest
from starlette.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient

from main import app, STORE
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
        self.commit_called = False
        self.closed = False
        self._events_queue = asyncio.Queue()
        self.ws_url = "wss://api.vachana.ai/stt/v3/stream"
        DummyPrismaStreaming.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.closed = True

    async def send_audio(self, pcm_data: bytes):
        self.audio_sent.append(pcm_data)

    async def commit(self):
        self.commit_called = True

    async def send_eof(self):
        await self.commit()

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
        self.ws_url = "wss://api.vachana.ai/api/v1/tts"
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
        self.closed = True


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
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/interview?protocol_version={PROTOCOL_VERSION}") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
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
        err_msg = json.loads(ws.receive_text())
        assert err_msg["type"] == "error"
        assert err_msg["code"] == "consent_required"


def test_ws_session_start_ack_and_flow():
    client = TestClient(app)
    with client.websocket_connect(f"/ws/interview?protocol_version={PROTOCOL_VERSION}") as ws:
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": True,
            "stt_model": "prisma-v2.5",
        }))

        ack = json.loads(ws.receive_text())
        assert ack["type"] == "session_ack"
        assert ack["status"] == "ok"
        assert ack["question_number"] == 1
        assert "question" in ack
        assert "session_id" in ack

        # Verify session is persisted in SQLiteStore
        stored = STORE.get_session(ack["session_id"], None)
        assert stored is not None
        assert stored["state"]["track"] == "agentic"

        ws.close()


def test_ws_binary_audio_forwarding():
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

        # Drain until state is listening
        for _ in range(5):
            msg = ws.receive()
            if "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                if data.get("type") == "turn_state" and data.get("raw_state") == "listening":
                    break

        pcm_frame = b"\x05" * PCM_FRAME_BYTES
        ws.send_bytes(pcm_frame)

        # Allow ingest queue processing
        assert len(DummyPrismaStreaming.instances) > 0
        prisma_instance = DummyPrismaStreaming.instances[0]

        ws.send_text(json.dumps({"type": "ping"}))
        for _ in range(5):
            msg = ws.receive()
            if "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                if data.get("type") == "pong":
                    break

        assert len(prisma_instance.audio_sent) >= 1
        ws.close()


def test_slow_client_detection():
    from ws_router import _SessionContext, _enqueue_or_drop

    ctx = _SessionContext("test-id", "agentic", "en-IN", "prisma-v2.5", consent=True)
    small_q = asyncio.Queue(maxsize=2)

    asyncio.run(_enqueue_or_drop(small_q, "item-1", ctx))
    asyncio.run(_enqueue_or_drop(small_q, "item-2", ctx))
    assert small_q.full()
    assert ctx.metrics.dropped_frames == 0

    asyncio.run(_enqueue_or_drop(small_q, "item-3", ctx))
    assert ctx.metrics.dropped_frames == 1
    assert small_q.qsize() == 2
    assert small_q.get_nowait() == "item-2"
    assert small_q.get_nowait() == "item-3"


def test_candidate_barge_in():
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

        # Candidate interrupts during question playback
        ws.send_text(json.dumps({
            "type": "barge_in",
            "generation_id": 1,
        }))

        # Server should transition to listening and update state
        found_listening = False
        for _ in range(5):
            msg = ws.receive()
            if "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                if data.get("type") == "turn_state" and data.get("raw_state") == "listening":
                    found_listening = True
                    break

        assert found_listening is True
        ws.close()


def test_end_interview_early():
    client = TestClient(app)
    with client.websocket_connect("/ws/interview") as ws:
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "software",
            "language": "en-IN",
            "consent_given": True,
        }))

        ack = json.loads(ws.receive_text())
        sid = ack["session_id"]

        # User clicks End interview early
        ws.send_text(json.dumps({
            "type": "end_interview",
            "session_id": sid,
        }))

        # Server sends complete state and metrics
        found_complete = False
        for _ in range(10):
            try:
                msg = ws.receive()
                if "text" in msg and msg["text"]:
                    data = json.loads(msg["text"])
                    if data.get("type") == "turn_state" and data.get("state") == "Complete":
                        found_complete = True
                        break
            except Exception:
                break

        assert found_complete is True
        ws.close()

    # Session in SQLiteStore must be persisted and accessible
    stored = STORE.get_session(sid, None)
    assert stored is not None
    assert stored["state"]["track"] == "software"


def test_transcript_correction_endpoint():
    client = TestClient(app)
    # Start session via REST
    res = client.post("/api/session", json={"track": "ai", "language": "en-IN"})
    assert res.status_code == 200
    sid = res.json()["session_id"]

    # Submit answer
    ans_res = client.post("/api/answer", json={
        "session_id": sid,
        "text": "I built a model with PyTorch and evaluated precision."
    })
    assert ans_res.status_code == 200

    # Candidate corrects transcript post-call
    corr_res = client.post(f"/api/sessions/{sid}/correct", json={
        "question_index": 0,
        "corrected_text": "I built a classification model with PyTorch, split the data, and evaluated precision and recall."
    })
    assert corr_res.status_code == 200
    body = corr_res.json()
    assert body["corrected"] is True
    assert "classification" in body["answer"]["transcript"]
    assert body["answer"]["feedback"]["score"] >= 0

    # Verify report reflects corrected answer
    report = client.get(f"/api/report/{sid}").json()
    assert len(report["results"]) == 1
    assert "classification" in report["results"][0]["transcript"]
