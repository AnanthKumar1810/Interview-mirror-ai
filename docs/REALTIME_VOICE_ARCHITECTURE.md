# InterviewMirror realtime voice status

## Implemented path

The browser captures 16 kHz mono PCM through an AudioWorklet and sends 1,024-byte frames over `/ws/interview`. FastAPI forwards them to Gnani Prisma. A final Prisma transcript is shown for candidate review. The existing REST `/api/answer` session evaluates the **edited** answer and owns the next question. The existing `/api/speak` REST endpoint supplies Gnani Timbre question audio. The WebSocket connection is closed after answer submission; the next question opens a new connection.

This is streaming STT with review-first REST evaluation and TTS. It is **not** a full concurrent STT -> Evon -> streaming TTS agent. Evon is unavailable with the current STT/TTS-only key. The current rubric is labelled *uncalibrated practice guidance* and must not be represented as Gnani semantic evaluation.

`gnani_streaming.py` also has a documented Timbre WebSocket adapter. It has been exercised against the live provider, but the browser interview route does not yet use it. A future unified route must bind to the same persisted interview session and wait for transcript approval before evaluation.

## Official provider contract

- [Prisma streaming documentation](https://docs.gnani.ai/api/STT/stt-websocket): `wss://api.vachana.ai/stt/v3/stream`; configuration goes in upgrade headers (`x-api-key-id`, `language_code`, `model`, `x-sample-rate`, `format`, `x-min-silence-ms`). Send 1,024-byte PCM frames. `{"type":"commit"}` flushes an utterance. Final text arrives as `{"type":"transcript","text":"...","is_final":true}`.
- [Timbre streaming documentation](https://docs.gnani.ai/api/TTS/tts-websocket): `wss://api.vachana.ai/api/v1/tts`; the request specifies `audio_config` with raw PCM at 16 kHz. Audio arrives as base64 in JSON `data.audio`; `type=complete` ends synthesis.

Prisma's built-in VAD is configured at 700 ms in the adapter. This is a silence threshold, not an end-to-end latency target. The AudioWorklet emits 32 ms frames; browser scheduling and provider processing add delay.

## Live probe on 2026-11-13

The supplied local Gnani key connected to both official WebSocket endpoints. One English Timbre-to-Prisma round trip produced 56 TTS audio chunks (97,280 raw PCM bytes). First TTS chunk arrived 4,412 ms after synthesis request; TTS completed in 5,237 ms. Prisma's final transcript was `hello this is a short test of the interview voice`, received 8,570 ms after audio streaming began, **including** the roughly 3-second audio transmission. These are one-sample provider measurements, not p50/p95 or a browser-to-speaker benchmark. No 400-600 ms claim is supported.

The local probe script lives outside the repository and reads the key directly from the user's private file. The key, generated audio and provider messages are not committed.

## Setup and test

Install `requirements-dev.txt` for tests. Configure `GNANI_API_KEY` in the local server environment. Run `python -m pytest -q` and `python main.py`. The REST interview remains the authoritative path for question order, transcript edits, scoring and reports. The WebSocket route is local-only by default because it has no per-user authentication. Remote access requires `INTERVIEWMIRROR_WS_ALLOW_REMOTE=1` and must be placed behind authentication and rate limiting before public deployment.

The automated suite uses provider mocks and does not spend API credits. A live provider probe confirmed one TTS and one STT utterance. A browser microphone end-to-end run, multilingual STT quality, repeated latency distribution and Evon-based semantic evaluation remain unverified.
