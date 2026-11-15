"""Gnani Prisma v2.5 / Timbre v2.5 REST integrations.

Official docs:
https://docs.gnani.ai/api/STT/speech-to-text
https://docs.gnani.ai/api/TTS/tts-inference

Important: this is a SERVER-SIDE API client. Never send the Gnani key to the browser.
"""
from __future__ import annotations

import os
import json
import struct
import httpx

STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
# All of these voices are listed for Timbre v2.5, in the corresponding language.
VOICE = {"en-IN": "Pranav", "te-IN": "Suhana", "hi-IN": "Nalini"}


class GnaniError(RuntimeError):
    """Expected, non-sensitive error that the UI can display."""


def _finalize_wav_sizes(audio: bytes) -> bytes:
    """Fix RIFF/data size sentinels used by Gnani's completed REST WAV response.

    A streamed WAV writer may leave 0xffffffff in RIFF and data length fields.
    REST returns the complete binary body, so finalize those two lengths from
    the received byte count before exposing it to normal WAV decoders. Other
    malformed/truncated chunks are rejected instead of guessed.
    """
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise GnaniError("Gnani Timbre did not return a valid WAV recording.")
    result = bytearray(audio)
    sentinel = 0xFFFFFFFF
    riff_size = struct.unpack_from("<I", result, 4)[0]
    offset = 12
    data_sentinel = False
    found_data = False
    found_fmt = False
    while offset + 8 <= len(result):
        chunk_id = bytes(result[offset:offset + 4])
        chunk_size = struct.unpack_from("<I", result, offset + 4)[0]
        payload_start = offset + 8
        if chunk_size == sentinel:
            if chunk_id != b"data" or payload_start > len(result):
                raise GnaniError("Gnani Timbre returned malformed WAV chunk sizes.")
            chunk_size = len(result) - payload_start
            if chunk_size % 2:
                raise GnaniError("Gnani Timbre returned an incomplete PCM sample.")
            struct.pack_into("<I", result, offset + 4, chunk_size)
            data_sentinel = True
        elif payload_start + chunk_size > len(result):
            raise GnaniError("Gnani Timbre returned a truncated WAV chunk.")

        if chunk_id == b"fmt ":
            if chunk_size < 16:
                raise GnaniError("Gnani Timbre returned an invalid WAV format chunk.")
            found_fmt = True
        elif chunk_id == b"data":
            found_data = True

        next_offset = payload_start + chunk_size + (chunk_size & 1)
        if next_offset > len(result):
            raise GnaniError("Gnani Timbre returned a truncated WAV chunk.")
        offset = next_offset

    if offset != len(result) or not found_fmt or not found_data:
        raise GnaniError("Gnani Timbre did not return a complete WAV recording.")
    actual_riff_size = len(result) - 8
    if riff_size == sentinel or data_sentinel:
        struct.pack_into("<I", result, 4, actual_riff_size)
    elif riff_size != actual_riff_size:
        raise GnaniError("Gnani Timbre returned inconsistent WAV container sizes.")
    return bytes(result)


class GnaniClient:
    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self.api_key = (api_key if api_key is not None else os.getenv("GNANI_API_KEY", "")).strip()
        self.client = client or httpx.Client(timeout=httpx.Timeout(65.0, connect=10.0))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and self.api_key.lower() not in {
            'your_actual_api_key', 'your_actual_api_key_here', 'your-key-here',
            'paste_your_key_here', '<api-key>', 'replace_me'
        }

    def _headers(self) -> dict[str, str]:
        if not self.enabled:
            raise GnaniError("Gnani API key is missing. Add GNANI_API_KEY in .env and restart the backend.")
        return {"X-API-Key-ID": self.api_key}

    def _post(self, url: str, **kwargs) -> httpx.Response:
        try:
            response = self.client.post(url, headers=self._headers(), **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            # Avoid surfacing response bodies or accidental secrets to browser or logs.
            if code in (401, 403):
                reason = "API key is invalid, lacks access or has insufficient credits"
            elif code == 429:
                reason = "provider rate limit hit; wait for the previous request to finish"
            elif code == 400:
                reason = "provider rejected the parameters or media format"
            elif code in (408, 500, 502, 503, 504):
                reason = "provider is temporarily unavailable"
            else:
                reason = "provider rejected the request"
            raise GnaniError(f"Gnani request failed ({code}): {reason}.") from exc
        except httpx.TimeoutException as exc:
            raise GnaniError("Gnani request timed out; retry with a shorter recording.") from exc
        except httpx.RequestError as exc:
            raise GnaniError("Could not reach Gnani; check your network or provider availability.") from exc

    def transcribe(self, audio_wav: bytes, language: str, bias_terms: list[str] | None = None,
                   *, model_version: str = "prisma-v2.5") -> dict:
        if model_version not in {"prisma-v2.5", "prisma-v3.0"}:
            raise GnaniError("Unsupported Prisma model.")
        v3_hints = language.split(",") if model_version == "prisma-v3.0" else []
        valid_v3_hints = (1 <= len(v3_hints) <= 4 and all(hint in VOICE for hint in v3_hints)
                          and len(set(v3_hints)) == len(v3_hints))
        if language not in VOICE and not (model_version == "prisma-v3.0"
                                          and (language == "indic-auto" or valid_v3_hints)):
            raise GnaniError("Unsupported transcription language.")
        # Official docs: omit model for default Prisma v2.5. The provider only
        # needs audio_file and language_code; format=transcribe cleans punctuation.
        data = {"language_code": language, "format": "transcribe"}
        if model_version == "prisma-v3.0":
            data.update({"model": "prisma-v3.0", "format": "codemix"})
        # Prisma v2.5: single letter-only words, paired with an allowed score.
        # Keep the list small and review the resulting transcript before scoring.
        terms = list(dict.fromkeys(term for term in (bias_terms or []) if term.isascii() and term.isalpha() and 4 <= len(term) <= 40))[:100]
        if terms and model_version == "prisma-v3.0":
            data["keyterms"] = json.dumps(terms)
        elif terms:
            data.update({"bias_list": json.dumps(terms), "bias_score": "1.0"})
        response = self._post(
            STT_URL,
            files={"audio_file": ("candidate.wav", audio_wav, "audio/wav")},
            data=data,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GnaniError("Gnani Prisma returned malformed JSON.") from exc
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise GnaniError("Gnani Prisma could not transcribe this recording.")
        transcript = payload.get("transcript")
        if not isinstance(transcript, str):
            raise GnaniError("Gnani Prisma response did not contain a transcript.")
        if not transcript.strip():
            raise GnaniError("No speech detected. Please record a clearer, longer answer.")
        if payload.get("truncated") is True:
            raise GnaniError("Prisma transcript was truncated; retry with shorter audio.")
        return {
            "transcript": transcript.strip(),
            "model": payload.get("model", model_version),
            "request_id": payload.get("request_id"),
            "detected_language_code": payload.get("detected_language_code"),
        }

    def synthesize(self, text: str, language: str) -> bytes:
        if language not in VOICE:
            raise GnaniError("Unsupported speech synthesis language.")
        if not text.strip():
            raise GnaniError("Question text cannot be empty.")
        body = {
            "text": text.strip(),
            "model": "timbre-v2.5",
            "voice": VOICE[language],
            "language": language,
            "speed": 1.0,
            "audio_config": {
                "encoding": "linear_pcm", "container": "wav",
                "num_channels": 1, "sample_rate": 24000, "sample_width": 2,
            },
        }
        response = self._post(TTS_URL, json=body)
        data = _finalize_wav_sizes(response.content)
        # Validate the full container instead of relying only on RIFF/WAVE magic.
        import io
        import wave
        try:
            with wave.open(io.BytesIO(data), "rb") as sound:
                valid = (sound.getnchannels() == 1
                         and sound.getsampwidth() == 2
                         and 8000 <= sound.getframerate() <= 48000
                         and sound.getnframes() > 0)
        except (wave.Error, EOFError, ValueError):
            valid = False
        if not valid:
            raise GnaniError("Gnani Timbre did not return a valid WAV recording.")
        return data



