import json
import uuid
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
from main import app, STORE
from auth_service import issue_token, hash_password
from ws_protocol import PROTOCOL_VERSION


def test_ws_auth_required_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("IM_AUTH_REQUIRED", "true")
    monkeypatch.setenv("IM_JWT_SECRET", "this-is-a-super-secret-jwt-key-32-chars-long!")

    client = TestClient(app)
    with client.websocket_connect(f"/ws/interview?protocol_version={PROTOCOL_VERSION}") as ws:
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": True,
        }))
        err = json.loads(ws.receive_text())
        assert err["type"] == "error"
        assert err["code"] == "unauthorized"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 1008


def test_ws_auth_required_accepts_valid_token(monkeypatch):
    monkeypatch.setenv("IM_AUTH_REQUIRED", "true")
    monkeypatch.setenv("IM_JWT_SECRET", "this-is-a-super-secret-jwt-key-32-chars-long!")

    # Create user in STORE
    email = f"test-ws-{uuid.uuid4().hex[:8]}@example.com"
    user_id = STORE.create_user(email, hash_password("Password123!"))
    token = issue_token(user_id)

    client = TestClient(app)
    with client.websocket_connect(f"/ws/interview?protocol_version={PROTOCOL_VERSION}&token={token}") as ws:
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": True,
        }))
        ack = json.loads(ws.receive_text())
        assert ack["type"] == "session_ack"
        sid = ack["session_id"]

        # Verify session in STORE is owned by user_id
        session_data = STORE.get_session(sid, user_id)
        assert session_data is not None
        assert session_data["state"]["owner_id"] == user_id
        ws.close()


def test_ws_rejects_cross_user_session_hijack(monkeypatch):
    monkeypatch.setenv("IM_AUTH_REQUIRED", "true")
    monkeypatch.setenv("IM_JWT_SECRET", "this-is-a-super-secret-jwt-key-32-chars-long!")

    # User A creates a session
    user_a = STORE.create_user(f"user-a-{uuid.uuid4().hex[:8]}@example.com", hash_password("Password123!"))
    token_a = issue_token(user_a)

    client = TestClient(app)
    with client.websocket_connect(f"/ws/interview?protocol_version={PROTOCOL_VERSION}&token={token_a}") as ws:
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": True,
        }))
        ack = json.loads(ws.receive_text())
        session_a_id = ack["session_id"]
        ws.close()

    # User B tries to hijack User A's session
    user_b = STORE.create_user(f"user-b-{uuid.uuid4().hex[:8]}@example.com", hash_password("Password123!"))
    token_b = issue_token(user_b)

    with client.websocket_connect(f"/ws/interview?protocol_version={PROTOCOL_VERSION}&token={token_b}") as ws:
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": True,
            "session_id": session_a_id,  # User B claiming User A's session
        }))
        err = json.loads(ws.receive_text())
        assert err["type"] == "error"
        assert err["code"] == "forbidden"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 1008
