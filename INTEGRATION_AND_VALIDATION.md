# InterviewMirror AI — Integration and Gnani Verification

## What was consolidated

Starting point: the tested `InterviewMirror-AI-Phase2-Evaluation-v3.zip`, which already integrated the earlier text MVP, the Gnani API client, evidence-linked evaluation, and adaptive questions. This unified build adds explicit compatibility endpoints for the **known route names** in the user's other session-based Windows application. **The source of that Windows application was not supplied**, so its UI behavior and exact multipart form fields cannot be guaranteed to match. Do not overwrite it without backing up the folder.

The Phase 4 Ollama improvements from a separate Work conversation were not available as source files. This build preserves v3's **optional** `OLLAMA_MODEL` qualitative feedback, and does not claim that any independent Phase 4 files were merged.

### Application structure

- `main.py`: FastAPI, session handling, interview lifecycle, reporting, audio-validation REST routes, and adapter routes.
- `app/main.py`: Windows-compatible import shim. Both `uvicorn main:app` and `uvicorn app.main:app` work from project root.
- `coach.py`: question bank, scoring helpers, optional Ollama qualitative feedback.
- `evaluation.py`: four-dimensional practice scoring with evidence excerpts.
- `adaptive.py`: localized second question chosen by scoring gaps.
- `gnani.py`: server-side Prisma v2.5 STT and Timbre v2.5 TTS clients with sanitized errors.
- `static/`: browser UI, microphone recording, 16k mono PCM16 WAV encoder, transcript review, evaluator display and session report.
- `verify_live.py`: explicit real-provider test script; consumes Gnani credits only when intentionally run.

### Main routes

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Backward-compatible backend health and whether key is configured |
| `GET /api/status` | UI configuration, tracks, languages, mock/live-key status |
| `GET /api/diagnostics` | No-secret diagnostic overview; never claims to prove live API access |
| `POST /api/session` | Start interview (v3 browser) |
| `POST /api/answer` | Evaluate one typed/transcribed answer |
| `GET /api/report/{id}` | Evidence-based final report |
| `POST /api/transcribe` | Validate/upload WAV then call Prisma |
| `POST /api/speak` | Question text to Timbre |
| `POST /api/sessions` | Compatibility session creation alias |
| `GET /api/sessions/{id}` | Compatibility status/answers |
| `POST /api/sessions/{id}/answers` | Compatibility multipart submission (`audio`, `transcript`, or `mock_transcript`) |
| `GET /api/sessions/{id}/question-audio` | Compatibility current question to Timbre |

These compatibility adapters share one session dictionary and one evaluation path. They are safe to use independently, but not guaranteed to be a drop-in API for an unseen Windows frontend.

## Why Gnani is called from FastAPI, not JavaScript

`X-API-Key-ID` credentials must remain on the backend. The browser can be inspected. Browser records and converts the microphone audio into mono PCM16 WAV at 16 kHz, then submits it as multipart data. FastAPI checks size, duration and format **before** sending any API request.

Prisma: `POST https://api.vachana.ai/stt/v3`, multipart `audio_file` and `language_code`; omitted `model` selects Prisma v2.5; `format=transcribe` returns cleaned speech. Maximum REST clip length 30 seconds. See https://docs.gnani.ai/api/STT/speech-to-text.

Timbre: `POST https://api.vachana.ai/api/v1/tts/inference`, JSON containing `text`, `model=timbre-v2.5`, voice/language, and `audio_config`; output is **binary WAV**. See https://docs.gnani.ai/api/TTS/tts-inference.

## Verification levels

1. **Source validation**: Python imports, environment and app startup.
2. **Offline unit and contract tests**: no Gnani credits; fake HTTP provider validates endpoints, authentication headers, audio MIME and error behavior.
3. **Live smoke test (required before competition submission)**: only on the user's computer after adding a real key to local `.env`; saves playable TTS audio and prints actual STT transcript; this consumes credits.
4. **Manual browser E2E**: listen to a question, record up to 28 seconds, check the displayed transcript, edit if necessary, submit, inspect feedback, and complete a 3-question session. Repeat in English and Telugu.

A **configured key is not evidence of a working provider**. `/api/diagnostics` intentionally always returns `gnani_live_verified: false` because it does not make a live call.

## Windows commands

From the extracted project root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

Open http://127.0.0.1:8001 and http://127.0.0.1:8001/api/diagnostics .

To run the **real** Gnani tests, add the key **privately** to `.env` (`GNANI_API_KEY=...`), restart Uvicorn, then in a *second* terminal:

```powershell
.\.venv\Scripts\python.exe verify_live.py --tts --language en-IN --output english-question.wav
.\.venv\Scripts\python.exe verify_live.py --tts --language te-IN --output telugu-question.wav
.\.venv\Scripts\python.exe verify_live.py --audio candidate-english.wav --language en-IN
.\.venv\Scripts\python.exe verify_live.py --audio candidate-telugu.wav --language te-IN
```

The two candidate WAV files must be **actual recorded voice clips**, 16kHz, 16-bit, mono, 0.2–30s. Use the app's built-in recorder for browser tests; to supply WAV files to the CLI script, record in an audio editor or convert to this format. Do not copy `.env` into a public repository or ZIP.

## Expected PASS evidence for submission

- TTS commands save non-empty, playable English and Telugu WAV files.
- STT commands return non-empty transcripts accurately reflecting the corresponding recordings.
- UI successfully records, transcribes, allows text corrections and saves responses.
- Three question flow completes; adaptive second question and report show evidence excerpts.
- Tests pass; failures and network outages show actionable messages without leaking keys.
- Final demo uses actual Gnani calls, not mock or synthetic transcripts.

## Limitations

- No real Gnani access was available inside this build session; all reported tests are offline.
- No persistence; sessions are in RAM and disappear on restart.
- Scores are transcript-pattern practice aids, **not validated technical correctness**.
- Browser voice features should be checked in Chrome or Edge on localhost rather than assuming VS Code's embedded browser supports audio decoding.
- On a real account, Gnani API authorization, credits and availability must be checked.
