# How I connected the Gnani APIs (and why)

## The boundary between your local app and a cloud speech provider

The API key belongs in `.env` on the **FastAPI server**, never in `static/app.js` or a frontend request. The frontend sends only a microphone recording and selected language. FastAPI attaches the key when it calls Gnani. This protects the key from the browser's Developer Tools and from accidental screenshots.

## Transcription: microphone -> transcript

1. **Browser microphone**: `navigator.mediaDevices.getUserMedia()` requests mic permission on `localhost` or HTTPS.
2. **Record**: `MediaRecorder` captures the browser-supported format, such as WebM/Opus.
3. **Convert**: Web Audio decodes the recording and combines channels, resamples to 16 kHz, and writes mono 16-bit PCM WAV. Why? A predictable WAV format is easier to validate, and a 28-second UI cap fits Gnani's 30-second REST limit.
4. **Upload**: frontend sends `FormData` with fields `audio` and `language` to `POST /api/transcribe`. The browser must not set `Content-Type` manually; it generates the multipart boundary.
5. **Validate**: FastAPI rejects unexpected MIME, huge files, WAVs that aren't 16 kHz mono 16-bit, and clips outside 0.2–30 seconds before spending API credits.
6. **Gnani call**: server sends `POST https://api.vachana.ai/stt/v3`, header `X-API-Key-ID`, `audio_file` and `language_code`, with `format=transcribe`. The documented default is Prisma v2.5 when `model` is omitted.
7. **Result**: server checks JSON and non-empty `transcript`; frontend puts the result in an editable answer field. User then submits the transcript for feedback. Empty transcripts and provider errors are shown honestly.

## Spoken interviewer: question -> audio

1. Frontend sends the question and language to `POST /api/speak`.
2. Backend chooses a documented voice: Pranav (`en-IN`), Suhana (`te-IN`), or Nalini (`hi-IN`).
3. Backend sends JSON to `https://api.vachana.ai/api/v1/tts/inference` with `model=timbre-v2.5`, voice, language and `audio_config={container:wav,encoding:linear_pcm}`.
4. Backend validates a WAV header and streams the binary response to the frontend as `audio/wav`.
5. Browser plays the question. Starting a new recording first stops question playback, so the microphone does not capture the interviewer's audio.

## Error handling

- Missing key: clear message, no pretend voice transcription.
- 400 provider response: invalid parameters or media format.
- 401/403: key, permission, or credits problem (actual cause needs dashboard/provider check).
- 429: rate limit; retry after active request finishes.
- Timeouts/5xx: provider/network issue; no invented transcript.
- Empty transcript: ask candidate to record again.

## Validated versus unvalidated

**Validated offline:** FastAPI routes, file validation, STT/TTS request structure, auth header, response parsing and safe failures, using mock HTTP responses (no credits). Ten automated tests pass.

**Not yet validated:** Your account credentials, real Gnani STT/TTS responses, actual live English/Telugu recordings and end-user sound quality. To validate live APIs you must configure `.env` on your own machine and test; never paste the key into ChatGPT.

## Windows test commands

From the extracted v2 directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Edit .env to insert your own GNANI_API_KEY; save, then restart.
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

Open `http://127.0.0.1:8001/api/status`. With the key loaded, the frontend enables the live voice controls; that **does not prove** credentials are valid. Test the **Listen** button, then record and stop within 28 seconds.

To independently test TTS against Gnani (uses API credits):

```powershell
.\.venv\Scripts\python.exe verify_live.py --tts --language en-IN
```

To test an existing *16kHz mono WAV*:

```powershell
.\.venv\Scripts\python.exe verify_live.py --audio .\your-answer.wav --language te-IN
```

## Project-version warning

This is based on the **12-file ZIP provided in our conversation**. Your *running* Windows project shown in screenshots is another code revision containing `app/main.py` and endpoints such as `/api/sessions/{session_id}/answers`; this updated ZIP uses `/api/session`, `/api/transcribe`, and `/api/speak`. Do not copy its source over your current running app. Keep the two builds separate; we need the newer revision's source to integrate it in place without losing its UI or its answer metrics.

## Official sources

- https://docs.gnani.ai/api/STT/speech-to-text
- https://docs.gnani.ai/api/TTS/tts-inference
- https://docs.gnani.ai/api/TTS/available-voices
