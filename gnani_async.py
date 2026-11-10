"""Async Gnani HTTP adapter for controlled voice pipeline experiments.

No network operation is performed at import time. Keep keys server-side and
use ``async with AsyncGnaniClient(...)`` to close owned HTTP connections.
"""
from __future__ import annotations

import io
import json
import os
import wave

import httpx

from gnani import GnaniError, STT_URL, TTS_URL, VOICE


class AsyncGnaniClient:
    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self.api_key = (api_key if api_key is not None else os.getenv("GNANI_API_KEY", "")).strip()
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(65.0, connect=10.0))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and self.api_key.lower() not in {
            "your_actual_api_key", "your_actual_api_key_here", "your-key-here",
            "paste_your_key_here", "<api-key>", "replace_me",
        }

    def _headers(self) -> dict[str, str]:
        if not self.enabled:
            raise GnaniError("Gnani API key is missing. Add GNANI_API_KEY to your local .env.")
        return {"X-API-Key-ID": self.api_key}

    async def __aenter__(self) -> "AsyncGnaniClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _post(self, url: str, **kwargs) -> httpx.Response:
        try:
            response = await self.client.post(url, headers=self._headers(), **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (401, 403):
                reason = "invalid credentials, insufficient access, or insufficient credits"
            elif code == 429:
                reason = "provider rate limit"
            elif code == 400:
                reason = "provider rejected parameters or media format"
            elif code in (408, 500, 502, 503, 504):
                reason = "provider temporarily unavailable"
            else:
                reason = "provider rejected the request"
            raise GnaniError(f"Gnani request failed ({code}): {reason}.") from exc
        except httpx.TimeoutException as exc:
            raise GnaniError("Gnani request timed out.") from exc
        except httpx.RequestError as exc:
            raise GnaniError("Could not reach Gnani provider.") from exc

    async def transcribe(self, audio_wav: bytes, language: str, bias_terms: list[str] | None = None) -> dict:
        if language not in VOICE:
            raise GnaniError("Unsupported transcription language.")
        data = {"language_code": language, "format": "transcribe"}
        terms = list(dict.fromkeys(term for term in (bias_terms or []) if term.isascii() and term.isalpha() and 4 <= len(term) <= 40))[:100]
        if terms:
            data.update({"bias_list": json.dumps(terms), "bias_score": "1.0"})
        response = await self._post(
            STT_URL,
            files={"audio_file": ("candidate.wav", audio_wav, "audio/wav")},
            data=data,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GnaniError("Gnani Prisma returned malformed JSON.") from exc
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise GnaniError("Gnani Prisma could not transcribe the audio.")
        transcript = payload.get("transcript")
        if not isinstance(transcript, str):
            raise GnaniError("Gnani Prisma response has no transcript.")
        if not transcript.strip():
            raise GnaniError("No speech detected in recording.")
        return {
            "transcript": transcript.strip(),
            "model": payload.get("model", "prisma-v2.5"),
            "request_id": payload.get("request_id"),
        }

    async def synthesize(self, text: str, language: str) -> bytes:
        if language not in VOICE:
            raise GnaniError("Unsupported speech synthesis language.")
        if not text.strip():
            raise GnaniError("Question text cannot be empty.")
        response = await self._post(
            TTS_URL,
            json={
                "text": text.strip(), "model": "timbre-v2.5", "voice": VOICE[language],
                "language": language, "speed": 1.0,
                "audio_config": {
                    "encoding": "linear_pcm", "container": "wav", "num_channels": 1,
                    "sample_rate": 24000, "sample_width": 2,
                },
            },
        )
        raw = response.content
        try:
            with wave.open(io.BytesIO(raw), "rb") as sound:
                valid = (
                    sound.getnchannels() == 1 and sound.getsampwidth() == 2
                    and 8000 <= sound.getframerate() <= 48000
                    and sound.getnframes() > 0
                )
        except (wave.Error, EOFError, ValueError):
            valid = False
        if not valid:
            raise GnaniError("Gnani Timbre returned invalid WAV audio.")
        return raw

