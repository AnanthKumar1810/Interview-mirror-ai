"""Offline, reproducible Phase 2 async I/O and voice pipeline tests."""
import asyncio
import io
import wave

import httpx
import pytest

from coach import QUESTION_BANK, evaluate
from gnani import GnaniError, STT_URL, TTS_URL
from gnani_async import AsyncGnaniClient
from voice_pipeline import AsyncVoicePipeline, VoiceStageError, summarize_latency


def wav_bytes(rate=24000, duration=0.1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x10\x00" * int(rate * duration))
    return buffer.getvalue()


class FakeVoiceProvider:
    def __init__(self, *, delay=0):
        self.events = []
        self.delay = delay

    async def transcribe(self, audio_wav, language):
        self.events.append("stt_start")
        await asyncio.sleep(self.delay)
        self.events.append("stt_end")
        return {"transcript": "I built a Python agent and wrote tests.", "model": "mock"}

    async def synthesize(self, text, language):
        self.events.append("tts_start")
        await asyncio.sleep(self.delay)
        self.events.append("tts_end")
        return wav_bytes()


def score_using_real_interviewmirror(transcript):
    return evaluate(transcript, QUESTION_BANK["agentic"][0], "en-IN", "agentic", 0)


def test_pipeline_uses_real_scorer_and_reports_all_stages_without_logging_content():
    provider = FakeVoiceProvider(delay=0.002)
    runner = AsyncVoicePipeline(provider, score_using_real_interviewmirror)
    result = asyncio.run(runner.run(b"fake-input", language="en-IN", reply_text="Next question"))
    assert provider.events == ["stt_start", "stt_end", "tts_start", "tts_end"]
    assert result.score["method"] == "transparent_concept_coverage_rubric_v2"
    assert 0 <= result.score["score"] <= 100
    assert result.transcript.startswith("I built")
    assert set(result.timings_ms) == {"stt", "scoring", "tts", "total"}
    assert result.timings_ms["total"] >= max(result.timings_ms["stt"], result.timings_ms["tts"])
    summary = result.safe_summary()
    assert "transcript" not in summary and "score" not in summary and "audio" not in summary


def test_tts_is_not_called_if_stt_times_out():
    provider = FakeVoiceProvider(delay=0.2)
    runner = AsyncVoicePipeline(provider, score_using_real_interviewmirror, stt_timeout_s=0.02)
    with pytest.raises(VoiceStageError) as exc:
        asyncio.run(runner.run(b"fake-input", language="en-IN", reply_text="Next question"))
    assert (exc.value.stage, exc.value.kind) == ("stt", "timeout")
    assert provider.events == ["stt_start"]


def test_rejects_invalid_transcript_without_scoring():
    class BadSTT(FakeVoiceProvider):
        async def transcribe(self, *_):
            return {"transcript": "  "}
    with pytest.raises(VoiceStageError, match="invalid_transcript"):
        asyncio.run(AsyncVoicePipeline(BadSTT(), lambda text: (_ for _ in ()).throw(AssertionError()))
                    .run(b"audio", language="en-IN", reply_text="Question"))


def test_provider_exception_is_sanitized():
    class ErrorSTT(FakeVoiceProvider):
        async def transcribe(self, *_):
            raise RuntimeError("sensitive provider payload")
    with pytest.raises(VoiceStageError, match="provider_error") as exc:
        asyncio.run(AsyncVoicePipeline(ErrorSTT(), score_using_real_interviewmirror)
                    .run(b"audio", language="en-IN", reply_text="Question"))
    assert "sensitive" not in str(exc.value)


def test_native_async_concurrency_overlaps_independent_calls():
    class ConcurrentProvider(FakeVoiceProvider):
        def __init__(self):
            super().__init__(delay=0.005)
            self.active = 0
            self.maximum = 0
        async def transcribe(self, *_):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(self.delay)
            self.active -= 1
            return {"transcript": "answer"}
    provider = ConcurrentProvider()
    runner = AsyncVoicePipeline(provider, lambda _: {"score": 80})
    async def run_many():
        return await asyncio.gather(*(runner.run(b"audio", language="en-IN", reply_text="Question")
                                      for _ in range(8)))
    results = asyncio.run(run_many())
    assert len(results) == 8
    assert provider.maximum > 1  # overlapping I/O, not 8 serialized requests


def test_nearest_rank_percentiles():
    result = summarize_latency(list(range(1, 21)))
    assert result == {"p50_ms": 10, "p95_ms": 19, "max_ms": 20, "samples": 20}
    with pytest.raises(ValueError):
        summarize_latency([])


def test_async_gnani_http_contract_with_mock_transport():
    seen = []
    async def handler(request):
        seen.append(request)
        assert request.headers["X-API-Key-ID"] == "test-key"
        if str(request.url) == STT_URL:
            body = request.content
            assert b'name="audio_file"' in body
            assert b'name="language_code"' in body
            assert b'te-IN' in body
            return httpx.Response(200, json={"success": True, "transcript": "నా ప్రాజెక్ట్", "model": "prisma-v2.5"})
        if str(request.url) == TTS_URL:
            assert b'"model":"timbre-v2.5"' in request.content
            assert b'Suhana' in request.content
            return httpx.Response(200, content=wav_bytes())
        return httpx.Response(404)
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with AsyncGnaniClient(api_key="test-key", client=http) as provider:
                stt = await provider.transcribe(wav_bytes(), "te-IN")
                speech = await provider.synthesize("హలో", "te-IN")
                return stt, speech
    transcript, audio = asyncio.run(call())
    assert transcript["transcript"] == "నా ప్రాజెక్ట్"
    assert audio.startswith(b"RIFF")
    assert len(seen) == 2


def test_async_gnani_rejects_http_failure_without_leaking_body():
    async def handler(request):
        return httpx.Response(401, json={"secret": "DO_NOT_SHOW"})
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with AsyncGnaniClient(api_key="test-key", client=http) as provider:
                await provider.transcribe(wav_bytes(), "en-IN")
    with pytest.raises(GnaniError) as exc:
        asyncio.run(call())
    assert "DO_NOT_SHOW" not in str(exc.value)
    assert "401" in str(exc.value)


def test_async_gnani_invalid_tts_wav_and_missing_key():
    async def handler(request):
        return httpx.Response(200, content=b"RIFF" + b"\x00" * 20)
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with AsyncGnaniClient(api_key="test-key", client=http) as provider:
                await provider.synthesize("Hello", "en-IN")
    with pytest.raises(GnaniError, match="invalid WAV"):
        asyncio.run(call())
    async def missing_key():
        async with AsyncGnaniClient(api_key="") as provider:
            await provider.synthesize("Hello", "en-IN")
    with pytest.raises(GnaniError, match="key is missing"):
        asyncio.run(missing_key())
