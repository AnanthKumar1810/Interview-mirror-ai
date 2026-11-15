"""Regressions from a real Gnani final-segment event trace.

These tests use controlled provider events; they do not spend API credits.
"""
import asyncio
import json

import ws_router
from gnani_streaming import PrismaEvent
from interview_state import InterviewState


def _listening_context():
    ctx = ws_router._SessionContext(
        "turn-regression", "agentic", "en-IN", "prisma-v2.5", True,
    )
    ctx.state_machine.transition(InterviewState.asking)
    ctx.state_machine.transition(InterviewState.listening)
    return ctx


def test_final_transcript_without_speech_end_advances_once(monkeypatch):
    finalized = []
    instances = []

    class Provider:
        def __init__(self, **kwargs):
            self.ws_url = "wss://api.vachana.ai/stt/v3/stream"
            self.commit_count = 0
            instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def send_audio(self, data):
            pass

        async def commit(self):
            self.commit_count += 1

        async def events(self):
            yield PrismaEvent(event="connected")
            yield PrismaEvent(event="speech_start")
            yield PrismaEvent(event="processing")
            final = PrismaEvent(
                event="transcript", transcript="I built an agent with Python.",
                is_final=True, segment_id="seg-1",
            )
            yield final
            yield final  # duplicate delivery must not duplicate the answer
            while True:
                await asyncio.sleep(.05)

    async def finalize(ctx):
        finalized.append(list(ctx.accumulated_segments))
        ctx.active = False

    monkeypatch.setattr(ws_router, "PrismaStreamingClient", Provider)
    monkeypatch.setattr(ws_router, "_calculate_pause_timeout", lambda ctx: .01)
    monkeypatch.setattr(ws_router, "_finalize_turn", finalize)
    ctx = _listening_context()
    asyncio.run(asyncio.wait_for(ws_router._live_prisma_stt(ctx), timeout=2))
    assert finalized == [["I built an agent with Python."]]
    assert instances[0].commit_count == 0


def test_missing_key_never_creates_a_candidate_answer(monkeypatch):
    class DisabledClient:
        enabled = False

    monkeypatch.setattr(ws_router, "GnaniClient", DisabledClient)
    ctx = _listening_context()
    asyncio.run(ws_router._fallback_vad_stt(ctx))
    messages = [json.loads(ctx.control_outgoing.get_nowait())
                for _ in range(ctx.control_outgoing.qsize())]
    assert any(m.get("code") == "stt_unavailable" for m in messages)
    assert not any(m.get("type") == "transcript" for m in messages)
    assert ctx.state_machine.answers == []
