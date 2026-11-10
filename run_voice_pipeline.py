"""Run Phase 2 mock concurrency demo or opted-in real Gnani batch-turn test.

No external calls without ``--wav``. Never prints API credentials or dumps audio.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from coach import QUESTION_BANK, evaluate
from audio_tools import inspect_pcm16_wav
from gnani_async import AsyncGnaniClient
from voice_pipeline import AsyncVoicePipeline, summarize_latency


class FakeVoiceProvider:
    async def transcribe(self, audio_wav: bytes, language: str) -> dict:
        await asyncio.sleep(0.035)
        return {"transcript": "I built an agent using Python tools and verified the fix with tests."}

    async def synthesize(self, text: str, language: str) -> bytes:
        await asyncio.sleep(0.025)
        return b"fake-audio-for-offline-demo-only"


def make_scorer(track: str, language: str):
    question = QUESTION_BANK[track][0]
    return lambda transcript: evaluate(transcript, question, language, track, 0)


async def demo(n: int) -> None:
    if not 1 <= n <= 100:
        raise ValueError("Demo calls must be between 1 and 100")
    runner = AsyncVoicePipeline(FakeVoiceProvider(), make_scorer("agentic", "en-IN"))
    results = await asyncio.gather(*[
        runner.run(b"fake-audio", language="en-IN", reply_text="Tell me about a failure.")
        for _ in range(n)
    ])
    by_stage = {
        stage: summarize_latency([result.timings_ms[stage] for result in results])
        for stage in ("stt", "scoring", "tts", "total")
    }
    print(json.dumps({
        "simulation_only": True,
        "note": "These are mocked network waits, not Gnani/LiveKit provider timings.",
        "concurrent_calls": n,
        "by_stage": by_stage,
    }, indent=2))


async def real(wav: Path, track: str, language: str, save_audio: Path | None, show_transcript: bool) -> None:
    load_dotenv(Path(__file__).parent / ".env")
    raw = wav.read_bytes()
    info = inspect_pcm16_wav(raw)
    if info["possibly_silent"]:
        raise ValueError("Recording seems silent; no provider credits used")
    question = QUESTION_BANK[track][1][language]
    async with AsyncGnaniClient() as provider:
        runner = AsyncVoicePipeline(provider, make_scorer(track, language))
        result = await runner.run(raw, language=language, reply_text=question)
    payload = {
        "simulation_only": False,
        "audio_validation": "valid_16k_mono_pcm16",
        "scoring_method": result.score.get("method"),
        "score_0_to_100": result.score.get("score"),
        **result.safe_summary(),
        "note": "Batch call timings; not first-audio latency or turn detection.",
    }
    if show_transcript:
        payload["transcript"] = result.transcript
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if save_audio:
        save_audio.write_bytes(result.audio)
        print(f"Saved TTS WAV: {save_audio}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Offline mock concurrency benchmark")
    parser.add_argument("--calls", type=int, default=20, help="Concurrent demo calls")
    parser.add_argument("--wav", type=Path, help="Opt-in live Gnani experiment with a 16 kHz mono PCM16 WAV")
    parser.add_argument("--track", choices=tuple(QUESTION_BANK), default="agentic")
    parser.add_argument("--language", choices=("en-IN", "te-IN", "hi-IN"), default="en-IN")
    parser.add_argument("--save-audio", type=Path, help="Optional TTS audio output (personal/local only)")
    parser.add_argument("--show-transcript", action="store_true", help="Print private transcript to local terminal")
    args = parser.parse_args()
    if args.demo == bool(args.wav):
        parser.error("Choose either --demo or --wav PATH")
    if args.demo:
        asyncio.run(demo(args.calls))
    else:
        asyncio.run(real(args.wav, args.track, args.language, args.save_audio, args.show_transcript))


if __name__ == "__main__":
    main()
