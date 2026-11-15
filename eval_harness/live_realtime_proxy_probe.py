"""One real-provider, synthetic-audio probe through the frontend WebSocket proxy.

Usage: python -m eval_harness.live_realtime_proxy_probe PATH_TO_LOCAL_KEY
Never prints or stores the key. This is transport verification, not candidate ASR quality.
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly
import websockets

from gnani import GnaniClient


def pcm16_16khz(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
        assert audio.getnchannels() == 1 and audio.getsampwidth() == 2
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float64)
        rate = audio.getframerate()
    from math import gcd
    divisor = gcd(rate, 16000)
    result = resample_poly(samples, 16000 // divisor, rate // divisor)
    return np.clip(result, -32768, 32767).astype("<i2").tobytes()


async def probe(key: str) -> dict:
    text = "I built a Python service with FastAPI and SQLite. It accepts user requests, stores results, and I tested its API with automated tests."
    voice = await asyncio.to_thread(GnaniClient(api_key=key).synthesize, text, "en-IN")
    pcm = pcm16_16khz(voice)
    listening = asyncio.Event()
    second_question = asyncio.Event()
    events: list[tuple[float, str, dict]] = []
    start = time.monotonic()
    async with websockets.connect("ws://127.0.0.1:8082/ws/interview?protocol_version=1.0", max_size=20_000_000) as socket:
        await socket.send(json.dumps({
            "type": "session_start", "protocol_version": "1.0", "track": "software", "language": "en-IN",
            "consent_given": True, "stt_model": "prisma-v2.5", "endpointing_policy": "adaptive",
            "target_questions": 3, "require_streaming": True,
        }))

        async def receive() -> None:
            async for raw in socket:
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                events.append((time.monotonic() - start, msg.get("type", ""), msg))
                if msg.get("type") == "turn_state" and msg.get("raw_state") == "listening" and msg.get("question_number") == 1:
                    listening.set()
                if msg.get("type") == "turn_state" and msg.get("raw_state") == "asking" and msg.get("question_number") == 2:
                    second_question.set()

        reader = asyncio.create_task(receive())
        try:
            await asyncio.wait_for(listening.wait(), 35)
            for offset in range(0, len(pcm), 1024):
                frame = pcm[offset:offset + 1024].ljust(1024, b"\0")
                await socket.send(frame)
                await asyncio.sleep(0.032)
            for _ in range(94):  # Three seconds of microphone silence after the answer.
                await socket.send(bytes(1024))
                await asyncio.sleep(0.032)
            try:
                await asyncio.wait_for(second_question.wait(), 30)
            except TimeoutError:
                pass
            await socket.send(json.dumps({"type": "end_interview", "session_id": next(
                (msg.get("session_id") for _, kind, msg in events if kind == "session_ack"), "")}))
        finally:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)

    transcripts = [(round(t, 3), msg.get("text", ""), bool(msg.get("is_final")), bool(msg.get("is_turn_final")))
                   for t, kind, msg in events if kind == "transcript"]
    return {
        "session_ack": any(kind == "session_ack" for _, kind, _ in events),
        "streaming_provider_connected": any(kind == "provider_event" and msg.get("detail", {}).get("provider") == "prisma"
                                            for _, kind, msg in events),
        "provider_interim_transcripts": sum(not segment_final for _, _, segment_final, _ in transcripts),
        "provider_segment_final_transcripts": sum(segment_final and not turn_final for _, _, segment_final, turn_final in transcripts),
        "turn_final_transcripts": sum(turn_final for _, _, _, turn_final in transcripts),
        "question_two_asking_at_s": next((round(t, 3) for t, kind, msg in events if kind == "turn_state"
                                           and msg.get("raw_state") == "asking" and msg.get("question_number") == 2), None),
        "first_transcript_at_s": transcripts[0][0] if transcripts else None,
        "errors": [msg.get("code") for _, kind, msg in events if kind == "error"],
        "event_trace": [f"{t:.2f}s {kind} {msg.get('raw_state', msg.get('event', ''))} {msg.get('question_number', '')}"
                        for t, kind, msg in events if kind in {"session_ack", "provider_event", "transcript", "turn_state", "error"}],
        "note": "Gnani-generated speech through the live proxy, not a person or physical microphone.",
    }


if __name__ == "__main__":
    secret = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
    if not secret:
        raise SystemExit("Key file is empty")
    print(json.dumps(asyncio.run(probe(secret)), indent=2))
