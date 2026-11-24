"""Opt-in LiveKit RTC worker. Run separately from the FastAPI WebSocket server.

Only Gnani handles speech. The existing deterministic interview engine handles
questions, feedback and reports; there is no hosted LLM in this pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, TurnHandlingOptions, cli
from livekit.plugins import gnani, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

import main
from gnani import VOICE
from rtc_policy import TurnLedger, turn_mode
from rtc_turn_lab import TurnLab, save_summary

load_dotenv(".env")
log = logging.getLogger(__name__)
server = AgentServer()


def provider_adapters(language: str):
    """Build the documented LiveKit Gnani adapters with a server-only key."""
    key = os.environ["GNANI_API_KEY"]
    return (
        gnani.STT(language=language, sample_rate=16000, api_key=key, use_streaming=True),
        gnani.TTS(language=language, voice=VOICE[language], model="timbre-v2.5",
                  sample_rate=16000, encoding="linear_pcm", container="raw",
                  synthesize_method="websocket", api_key=key),
    )


class InterviewAgent(Agent):
    def __init__(self, ctx: JobContext, session_id: str, owner_id: str | None,
                 language: str, initial_question: str):
        super().__init__(instructions="Use the deterministic interview engine; never generate a free-form score.")
        self.ctx = ctx
        self.session_id = session_id
        self.owner_id = owner_id
        self.language = language
        self.initial_question = initial_question
        self.ledger = TurnLedger()
        self._lock = asyncio.Lock()
        self._speaking = False
        self._current_question = initial_question
        self.turn_lab = TurnLab()

    async def send(self, data: dict) -> None:
        if self.ledger.closed:
            return
        await self.ctx.room.local_participant.publish_data(
            json.dumps(data, ensure_ascii=False), reliable=True, topic="im.control")

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        text = (new_message.text_content or "").strip()
        action = self.turn_lab.classify(text)
        if action == "empty":
            return
        if action == "backchannel":
            # VAD may have stopped audio before the final transcript arrives.
            handle = self.turn_lab.active_speech
            if handle is not None and getattr(handle, "interrupted", False) and not self.ledger.closed:
                self.turn_lab.active_speech = self.session.say(self._current_question)
            return
        async with self._lock:
            if self.ledger.closed:
                return
            if action == "repeat":
                self.turn_lab.active_speech = self.session.say(self._current_question)
                return  # Never score a request to repeat the question.
            question_number = self.ledger.question_number
            generation = self.ledger.start(question_number, text)
            if generation is None:
                return
            try:
                result = await asyncio.to_thread(
                    main.answer, main.AnswerRequest(session_id=self.session_id, text=text),
                    self.owner_id)
            except Exception:
                log.exception("Could not score RTC turn")
                await self.send({"type": "error", "message": "Could not save this answer"})
                return
            if not self.ledger.advance(generation, question_number):
                return
            if result.get("next_question"):
                self._current_question = result["next_question"]
            await self.send({"type": "transcript", "text": text, "is_final": True,
                             "question_number": question_number})
            await self.send({"type": "turn_state", "state": "Feedback ready",
                             "raw_state": "feedback", "question": result.get("next_question") or "",
                             "question_number": min(question_number + 1, 3),
                             "feedback": result["feedback"]})
            if result["completed"]:
                asyncio.create_task(self._finish(generation))
            else:
                # The SDK cancels the active SpeechHandle and TTS stream on a real
                # interruption. The generation check suppresses late application output.
                if self.ledger.valid_audio(generation):
                    self.turn_lab.active_speech = self.session.say(
                        result["conversational_prompt"] or result["next_question"])

    async def _finish(self, generation: int) -> None:
        if not self.ledger.valid_audio(generation):
            return
        try:
            handle = self.session.say("Thank you. Your practice report is ready.")
            self.turn_lab.active_speech = handle
            await handle.wait_for_playout()
            if self.ledger.valid_audio(generation):
                await self.send({"type": "turn_state", "state": "Completed",
                                 "raw_state": "completed", "question_number": 3})
        except Exception:
            log.exception("Could not finish RTC interview")


@server.rtc_session(agent_name="interview-mirror")
async def entrypoint(ctx: JobContext) -> None:
    metadata = json.loads(ctx.job.metadata or "{}")
    session_id = metadata.get("session_id", "")
    owner_id = metadata.get("owner_id")
    if ctx.room.name != f"im-{session_id}" or not session_id:
        raise ValueError("Invalid RTC dispatch")
    record = await asyncio.to_thread(main.STORE.get_session, session_id, owner_id)
    if record is None:
        raise ValueError("RTC interview is unavailable")
    state = record["state"]
    language = state["language"]
    question = main.current_question(main.Session(**{
        key: value for key, value in state.items() if key in main.Session.__dataclass_fields__
    }))
    if not question:
        raise ValueError("RTC interview has no pending question")
    stt, tts = provider_adapters(language)
    detector = MultilingualModel() if turn_mode(language) == "multilingual" else "vad"
    adaptive = os.getenv("IM_RTC_ADAPTIVE_INTERRUPTION", "false").lower() == "true"
    session = AgentSession(
        stt=stt, tts=tts, vad=silero.VAD.load(min_silence_duration=0.55),
        turn_handling=TurnHandlingOptions(
            turn_detection=detector,
            endpointing={"min_delay": 0.35, "max_delay": 2.5},
            interruption={"mode": "adaptive" if adaptive else "vad",
                          "false_interruption_timeout": 1.2,
                          "resume_false_interruption": True},
            preemptive_generation={"enabled": False},
        ),
    )
    agent = InterviewAgent(ctx, session_id, owner_id, language, question)
    stop = asyncio.Event()

    @ctx.room.on("participant_disconnected")
    def _left(_participant):
        stop.set()

    @ctx.room.on("data_received")
    def _control(data):
        if data.topic == "im.control" and data.data == b'{"type":"end"}':
            stop.set()

    @session.on("agent_state_changed")
    def _state(event):
        agent._speaking = event.new_state == "speaking"
        agent.turn_lab.agent_state(event.new_state)

    @session.on("user_state_changed")
    def _user_state(event):
        agent.turn_lab.user_state(event.new_state)

    @session.on("user_interruption_detected")
    def _interruption(_event):
        agent.turn_lab.interruption_detected()

    @session.on("agent_false_interruption")
    def _false_interruption(_event):
        agent.turn_lab.false_interruption()

    await ctx.connect()
    await ctx.wait_for_participant()
    await session.start(agent, room=ctx.room)
    await agent.send({"type": "session_ack", "session_id": session_id,
                      "question": question, "question_number": 1,
                      "total_questions": 3, "turn_detection": turn_mode(language)})
    agent.turn_lab.active_speech = session.say(question)
    try:
        await stop.wait()
    finally:
        agent.ledger.close()
        agent.turn_lab.cancel_speech()
        try:
            await session.aclose()
        finally:
            try:
                save_summary(agent.turn_lab.summary(), language=language,
                             mode="adaptive" if adaptive else "vad",
                             folder=os.getenv("IM_RTC_TURN_METRICS_DIR", ".data/rtc-turn-lab"))
            except OSError:
                log.exception("Could not save anonymous RTC turn metrics")


if __name__ == "__main__":
    cli.run_app(server)
