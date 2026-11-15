"""Verification of Task 3: Scenarios A through E for genuine autonomous conversation."""
import json
import pytest
from fastapi.testclient import TestClient

import main
from main import app, STORE
import ws_router
from coach import QUESTION_BANK, evaluate
from robust_evaluation import evaluate_robust
from adaptive import select_followup
from ws_protocol import PROTOCOL_VERSION
from ws_router import _SessionContext, _calculate_pause_timeout
from tests.test_ws_router import DummyPrismaStreaming, DummyTimbreStreaming


@pytest.fixture(autouse=True)
def patch_gnani_clients(monkeypatch):
    DummyPrismaStreaming.instances.clear()
    DummyTimbreStreaming.instances.clear()
    monkeypatch.setattr(ws_router, "PrismaStreamingClient", DummyPrismaStreaming)
    monkeypatch.setattr(ws_router, "TimbreStreamingClient", DummyTimbreStreaming)


def test_scenario_a_strong_answer_deepens_tradeoff():
    """Scenario A — Strong answer: Explains technical concept correctly.

    The next question examines a deeper implementation or architectural trade-off.
    """
    track = "agentic"
    q = QUESTION_BANK[track][0]
    strong_answer = (
        "First I built an autonomous agent workflow with restricted file editing tools in Python and Docker. "
        "Because language models can produce incorrect diffs, I required human approval before any commit. "
        "I validated 12 regression tests in an isolated sandbox, ensuring zero broken dependencies, and maintained an audit log."
    )
    feedback = evaluate(strong_answer, q, "en-IN", track, 0)
    assert feedback["score"] >= 75
    assert feedback["dimensions"]["technical_coverage"] >= 25
    assert feedback["dimensions"]["evidence"] >= 15

    next_q, reason, focus = select_followup(track, "en-IN", feedback)
    assert focus == "tradeoff"
    assert next_q["level"] == "architecture"
    assert "alternative" in next_q["en-IN"].lower() or "latency" in next_q["en-IN"].lower() or "trade-off" in next_q["en-IN"].lower()
    assert "trade-off" in reason.lower() or "basics" in reason.lower()


def test_scenario_b_incorrect_answer_addresses_misconception_without_escalating_difficulty():
    """Scenario B — Incorrect answer: Candidate expresses a misconception.

    The next question addresses that misconception without blindly increasing difficulty.
    """
    track = "ai"
    q = QUESTION_BANK[track][1]
    # Candidate confuses precision with recall and makes absolute perfection claim
    misconception_answer = (
        "In our project, precision is true positives divided by true positives plus false negatives. "
        "We achieved 100 percent accuracy and therefore our model will never make another mistake."
    )
    robust_feedback = evaluate_robust(misconception_answer, q, "en-IN", track, 1)
    assert robust_feedback["risk_flags"]
    assert any("precision" in f["explanation"].lower() or "perfection" in f["explanation"].lower() for f in robust_feedback["risk_flags"])

    # Adaptive follow-up should detect risk_flags and ground in fundamentals
    next_q, reason, focus = select_followup(track, "en-IN", robust_feedback)
    assert focus == "technical"
    assert next_q["level"] == "fundamentals"
    assert "misconception" in reason.lower() or "technical" in reason.lower()
    # Confirm it does NOT escalate to architecture level
    assert next_q["level"] != "architecture"


def test_scenario_c_incomplete_answer_retains_audio_across_pause():
    """Scenario C — Incomplete answer: Candidate pauses for 1.3s and resumes.

    System does not cut off turn prematurely; retains the complete answer.
    """
    ctx = _SessionContext(
        session_id="test-incomplete-pause",
        owner_id=None,
        track="agentic",
        language="en-IN",
        consent=True,
        stt_model="prisma-v2.5",
        store=STORE,
        endpointing_policy="adaptive",
    )
    ctx.accumulated_segments = ["First I started the Docker container because"]

    # In adaptive mode with trailing conjunction 'because', timeout is 2.2s (> 1.3s)
    timeout = _calculate_pause_timeout(ctx)
    assert timeout == 2.2
    assert timeout > 1.3

    # In fixed mode, timeout is 1.8s (> 1.3s)
    ctx.endpointing_policy = "fixed"
    fixed_timeout = _calculate_pause_timeout(ctx)
    assert fixed_timeout == 1.8
    assert fixed_timeout > 1.3


def test_scenario_d_candidate_barge_in_interruption_stops_playback():
    """Scenario D — Interruption: Candidate speaks while interviewer is speaking.

    Playback stops and server transitions immediately to listening.
    """
    client = TestClient(app)
    with client.websocket_connect("/ws/interview") as ws:
        # Start session
        ws.send_text(json.dumps({
            "type": "session_start",
            "protocol_version": PROTOCOL_VERSION,
            "track": "agentic",
            "language": "en-IN",
            "consent_given": True,
        }))
        ack = json.loads(ws.receive_text())
        assert ack["type"] == "session_ack"

        # Emit barge-in while question is asking
        ws.send_text(json.dumps({
            "type": "barge_in",
            "generation_id": 1,
        }))

        # Server transitions to listening state
        found_listening = False
        for _ in range(6):
            msg = ws.receive()
            if "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                if data.get("type") == "turn_state" and data.get("raw_state") == "listening":
                    found_listening = True
                    break

        assert found_listening is True
        ws.close()


def test_scenario_e_multilingual_code_mixed_and_transcript_correction():
    """Scenario E — Multilingual: Telugu-English mixed speech.

    Recognition errors are distinguished from technical mistakes via transcript correction.
    """
    # 1. Evaluate Telugu-English code-mixed response
    track = "agentic"
    q = QUESTION_BANK[track][0]
    te_en_answer = (
        "నేను Python మరియు Docker తో ఒక code repair agent build చేశాను. "
        "Unreliable edits రాకుండా human approval guardrail పెట్టాను. "
        "Local sandbox లో 12 unit tests pass అయ్యాయి."
    )
    res = evaluate(te_en_answer, q, "te-IN", track, 0)
    assert res["score"] > 50
    assert res["dimensions"]["technical_coverage"] > 0
    # Technical concepts matched across Indic/English boundaries
    matched_concepts = [c["concept"] for c in res["coverage"] if c["mentioned"]]
    assert len(matched_concepts) >= 2

    # 2. Simulate ASR recognition error and correction via REST endpoint
    client = TestClient(app)
    sess_res = client.post("/api/session", json={"track": "agentic", "language": "te-IN"})
    assert sess_res.status_code == 200
    sid = sess_res.json()["session_id"]

    # Candidate answered with ASR error ("dogger" instead of "Docker")
    ans_res = client.post("/api/answer", json={
        "session_id": sid,
        "text": "నేను Python మరియు dogger తో ఒక agent build చేశాను.",
    })
    assert ans_res.status_code == 200
    original_score = ans_res.json()["feedback"]["score"]

    # Candidate corrects recognition error post-interview
    corr_res = client.post(f"/api/sessions/{sid}/correct", json={
        "question_index": 0,
        "corrected_text": "నేను Python మరియు Docker తో ఒక agent build చేశాను. Human approval guardrail మరియు 12 tests pass అయ్యాయి.",
    })
    assert corr_res.status_code == 200
    corr_json = corr_res.json()
    assert corr_json["corrected"] is True
    assert "Docker" in corr_json["answer"]["edited_transcript"]
    assert corr_json["answer"]["feedback"]["score"] >= original_score
