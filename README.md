# InterviewMirror AI — Gnani Voice Evaluation & Noise Upgrade

See [the 2026-11-14 live first-answer fix and verification](docs/LIVE_TURN_FIX_2026-11-14.md) for the current hands-free streaming status and remaining device-level tests.

**Build updated 10 Nov 2026 — account progress review, Prisma vocabulary hints and scoring regression controls.** An existing FastAPI + Prisma/Timbre technical interview practice system with implemented risk-aware scoring, opt-in speech enhancement, score regression gates and explicit voice-data consent.

See [three-report reconciliation](docs/REPORT_RECONCILIATION.md) for findings verified against this source version. The Progress review view reads account-owned sessions from SQLite, including transcripts and feedback. The scorer now flags dense, disconnected keyword lists, but remains an uncalibrated practice aid. Prisma v2.5 word boosting is limited to single letter-only technical terms from the selected interview focus and still requires transcript review.

**Measured locally:** 9-case synthetic dataset with 0 human-reviewed labels; among 2 developer-defined adversarial probes, scores >=70 changed from 1/2 (baseline) to 0/2 (new scorer). This does not establish real-world scoring validity. Live Gnani STT/TTS and a small human-recorded Hindi/Telugu speech check are now documented in [live results](docs/LIVE_GNANI_RESULTS_2026-11-13.md). No noisy Telugu interview WER or live Evon evaluation has been measured.

**Implementation guides:** [Architecture](docs/ARCHITECTURE.md) · [Gnani engineering scope](docs/GNANI_VOICE_ENGINEERING_SCOPE.md) · [Deployment and security](docs/DEPLOYMENT_AND_SECURITY.md) · [Changelog](docs/IMPLEMENTATION_CHANGELOG.md).

**Getting started:** use Python 3.13, run `python -m pip install -r requirements-dev.txt`, `python -m pytest -q`, `python -m eval_harness.compare_robust`, then `python -m uvicorn main:app --reload --port 8001`. Set `GNANI_API_KEY` **only in your local `.env`** to test real STT/TTS. The default enhancement is **off**, with experimental spectral and optional DeepFilterNet3 choices. The UI asks for consent before forwarding recordings to Gnani.

**Production disclaimer:** user accounts, Argon2 password hashes, bearer authentication and SQLite persistence are now implemented and tested. Expert-calibrated scores, live real-provider benchmarking and public deployment controls are still outstanding; see the security runbook.

With the available Gnani STT/TTS key, follow the [STT/TTS-only delivery plan](docs/GNANI_STT_TTS_ONLY_PLAN.md). The live app's numeric feedback is an uncalibrated text-based practice rubric. The Gnani Evon semantic A/B/C experiment is separate and awaits actual Evon access.

The larger [paired human-recorded ASR engineering check](docs/ENGINEERING_ASR_EVALUATION_2026-11-13.md) reports 24 Hindi/Telugu clips, 48 first-attempt Prisma calls, failure/retry behavior, exact-script WER/CER and latency. Its public benchmark code is `eval_harness/engineering_asr.py`; transcript-level data and the key stay local.

---

## Current authenticated storage and noise benchmarking

- [Authentication and durable SQLite](docs/AUTH_AND_STORAGE.md) — set `IM_AUTH_REQUIRED=true`, configure a random `IM_JWT_SECRET`, and use the signup form. With `IM_ENV=production`, invalid auth configuration fails closed.
- [Independent noise quality measurements](docs/NOISE_SEPARATE_EVALUATION.md) — 4 synthetic, paired audio fixtures and reproducible signal quality evaluation. Real Gnani ASR WER has not been measured.
- [Expert scoring reference datasets](docs/EXPERT_LABEL_RESOURCES.md) — SemEval labelled short answers and interview question/rubric resources, not direct expert interview scores.
- **Current offline test suite:** `python -m pytest -q` (83 passed in this audit). No real provider credentials were available to these tests.
- Keep `.env`, `.data`, WAV files and sensitive reports out of public GitHub commits.

---

## Earlier build history and notes

# InterviewMirror AI — Submission Preparation Build

**A GitHub-ready, offline-tested English/Telugu technical interview practice demo.**

This release preserves the unified project's Gnani Prisma STT, Timbre TTS, three-question interview, evidence-linked practice rubric, curated adaptive follow-ups, and final report. It adds a **safe local audio preflight** so microphone recording, audio encoding, playback, and saving can be tested **without a Gnani API key**.

> **Historical archive status (superseded):** 35 offline automated tests passed in an earlier source archive. Earlier user screenshots of a local build showed automatic transcription and question playback, but this exact archive was not independently authenticated against Gnani, and its parity with the original Windows checkout is unconfirmed. Do not overwrite the Windows checkout without comparing files.

## Internship preparation: Phase 1 evaluation harness

A new, independently tested evaluation harness and CI score-regression gate are documented in **[PHASE1_EVALUATION_GUIDE.md](PHASE1_EVALUATION_GUIDE.md)**. Its 9-case dataset is synthetic and **not human-labelled**; heuristic repeatability is not proof of validity. The optional Ollama numerical judge is experimental and disconnected from the live app.

## Windows quick start

1. Unzip and open the extracted `InterviewMirrorAI-GitHub-Ready` folder in VS Code or PowerShell.
2. Run this from the project folder:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\QUICKSTART_WINDOWS.ps1
   ```

3. When you see that Uvicorn is running, open **http://127.0.0.1:8001**.

The script installs the dependencies in `.venv`, creates `.env` from `.env.example` if missing, runs offline tests, and launches Uvicorn. It doesn't contact Gnani unless you manually request a live speech operation after adding a key.

If PowerShell says `QUICKSTART_WINDOWS.ps1` does not exist, you're in the wrong extracted directory (for example, the older `Gnani-Live-v2` folder). Run `Get-ChildItem -Name` and confirm `QUICKSTART_WINDOWS.ps1` is present.

## Test your microphone *without Gnani*

1. Leave `.env` with `GNANI_API_KEY=` blank.
2. Click **Start interview**, then **Record answer**.
3. Speak for 3–10 seconds; click **Stop recording**.
4. Wait for **Local audio check** showing clip duration, audio format, and input-level warning if needed.
5. Click **Replay recording** to listen, or **Save WAV** to keep a copy for later live Prisma testing.
6. Type the answer in the text box, click **Get feedback**, and complete the three-question interview.

**Why this matters:** a broken microphone/encoder can be diagnosed without wasting credits. The local preflight (`POST /api/audio/check`) validates the WAV but does **not** generate a transcript, contact Gnani, or store audio. WAV remains temporarily in the browser until the next question/restart; save it before moving on if you need the file. The actual voice input should be intelligible when replayed; the signal-level estimate alone does not prove speech quality.

## Enable real Gnani later

1. Open `.env` locally and add `GNANI_API_KEY=...`. **Never send the key in chat or commit `.env` to Git.**
2. Restart Uvicorn.
3. The homepage displays **KEY LOADED (UNVERIFIED)**. This does **not** mean Gnani authenticated successfully.
4. Try **Listen to question** (Timbre) and record a short real answer (Prisma). The app checks WAV characteristics *before* attempting an STT call. Calls may consume Gnani credits.
5. Verify with the included `verify_live.py` and repeat in English (`en-IN`) and Telugu (`te-IN`). Consult `GO_LIVE_CHECKLIST.md`.

## Important routes

| Endpoint | Purpose |
|---|---|
| `/api/health`, `/api/status`, `/api/diagnostics` | Local configuration, never proofs of live authorization |
| `POST /api/session`, `POST /api/answer` | Three-question practice interview |
| `GET /api/report/{session_id}` | Downloadable JSON practice report |
| **`POST /api/audio/check`** | **New: free local microphone/WAV format check** |
| `POST /api/transcribe` | Real Prisma STT; key required and quiet audio rejected |
| `POST /api/speak` | Real Timbre TTS; key required |
| `/api/sessions/...` | Compatibility routes for known older route names, not a guaranteed UI drop-in |

## Current limitations

- Gnani API key and credits were not available during implementation. No real-provider success is claimed.
- Original Windows `app/main.py` UI wasn't supplied; this release uses the separately tested unified interface.
- Browser microphone capture must be manually checked in Chrome/Edge on localhost. This environment could run a simulated browser interaction, but administrator restrictions blocked testing actual local-host microphone permission.
- Score = evidence-linked **practice heuristic**, not fact-checked technical correctness, pronunciation measurement, or a hiring recommendation.
- **Historical limitation, now superseded:** the original build used in-memory sessions. This upgrade uses SQLite with optional authenticated user accounts; see the current guide below.

Implementation rationale: **[AUDIO_PREFLIGHT_AND_DESIGN.md](AUDIO_PREFLIGHT_AND_DESIGN.md)**. Submission and live testing: **[GO_LIVE_CHECKLIST.md](GO_LIVE_CHECKLIST.md)**. Existing integration notes: **[INTEGRATION_AND_VALIDATION.md](INTEGRATION_AND_VALIDATION.md)**.

## Publishing source code

Read **[PUBLISH_TO_GITHUB.md](PUBLISH_TO_GITHUB.md)** for safe GitHub creation, staging checks, and push commands. See **[PROJECT_STATUS.md](PROJECT_STATUS.md)** for a truthful inventory of what is and is not verified. The repository excludes `.env`, audio recordings, local databases, and caches.


