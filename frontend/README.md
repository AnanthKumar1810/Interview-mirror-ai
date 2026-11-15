# ClearView frontend integration

This folder incorporates the ClearView React/TanStack frontend from
[`AnanthKumar1810/clearview-app-preview`](https://github.com/AnanthKumar1810/clearview-app-preview)
at `57e0c40bc5c37ce44b92ebac698c776798746df2`. Its interview flow now uses
InterviewMirror's FastAPI WebSocket, Gnani Prisma streaming STT, Gnani Timbre
voice, and the backend's transcript-based practice report.

## Run locally

### One-command local stack with Docker

From the repository root, create a local environment file if needed and place
the Gnani STT/TTS key in that local file only:

```powershell
Copy-Item .env.example .env
# Edit .env locally and set GNANI_API_KEY. Never commit or share this file.
docker compose up --build
```

Open `http://127.0.0.1:8082/app/new`. Docker Compose runs the backend and
ClearView frontend together, waits for the backend health check, and connects
the frontend's `/api` and `/ws` proxy over the private Compose network. Both
ports are bound to loopback. This is a local development stack, not a public
production deployment; authentication is intentionally disabled for local
use. Do not expose these ports to the internet.

Stop it with `Ctrl+C`; use `docker compose down` to stop and
`docker compose down -v` only if you intentionally want to erase the local
SQLite volume and interview history.

### Manual local run

Open two PowerShell windows from the repository root. In the first:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_REALTIME_BACKEND.ps1 -KeyFile 'C:\path\to\your\private-key-file.txt'
```

The script reads the private key into the backend process environment and
starts FastAPI on `127.0.0.1:8002`. The key is never sent to the browser or
copied into this repository. The file must contain only the key.

In the second:

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 8082
```

Open `http://127.0.0.1:8082/app/new`. Use the Start button once. Grant
microphone access if your browser asks. The browser streams 16 kHz PCM frames
through `/ws/interview`; the frontend development server proxies `/ws` and
`/api` to FastAPI on port 8002. The interviewer automatically detects the end
of an answer and asks the next question. Prisma events update the transcript
while streaming when the provider emits partial text. The interface requires
the Prisma streaming connection; it reports an error rather than silently
switching to a delayed REST transcript.

`npm run build`, `npx tsc --noEmit`, and `npm test` verify the frontend. The
Python suite is run from the repository root with `python -m pytest -q`.

## Current scope

- Three live tracks: Software Engineering, Machine Learning, Agentic AI.
- English, Telugu, Hindi; three questions per session.
- Gnani Prisma v2.5 streaming recognition and Gnani Timbre v2.5 voice.
- Adaptive follow-ups use the backend's deterministic policy. Numeric feedback
  is an uncalibrated transcript rubric. Evon and translation are unavailable
  with the current STT/TTS-only key.
- Reports are stored in the backend SQLite database. The browser stores a
  local index for history and progress; clearing browser data removes that
  index, while backend retention follows its own configuration.

For production hosting, the frontend must be built and deployed to a supported
TanStack Start target, with `/api/*` and `/ws/*` routed from the frontend origin
to FastAPI. Configure authentication, TLS, WebSocket origin checks, shared
rate limits, and persistent encrypted storage before allowing remote users.
The Docker Compose frontend is a Vite development server, not a production
frontend image. The
Lovable source's browser speech recognition and local demo scoring are not used
by the live interview route.

### Optional per-answer noise comparison

In the setup format step, users may enable a spectral-filter comparison. It is off by default. The server preserves the original Prisma streaming path for live transcript and scoring, then sends one additional filtered copy to Prisma after each answer. The interface shows both transcripts and timing and labels the result as a text comparison, not an accuracy score. Audio is held in memory for at most 30 seconds and discarded; the additional request uses STT credits and adds delay. See `../docs/NOISE_SEPARATE_EVALUATION.md`.
