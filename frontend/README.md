# ClearView frontend integration

This folder incorporates the ClearView React/TanStack frontend from
[`AnanthKumar1810/clearview-app-preview`](https://github.com/AnanthKumar1810/clearview-app-preview)
at `57e0c40bc5c37ce44b92ebac698c776798746df2`. Its interview flow now uses
InterviewMirror's FastAPI WebSocket, Gnani Prisma streaming STT, Gnani Timbre
voice, and the backend's transcript-based practice report.

## Run locally

Open two PowerShell windows from the repository root. In the first:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_REALTIME_BACKEND.ps1 -KeyFile 'C:\Users\Siddhu\Desktop\api.env.txt'
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

For production hosting, route `/api/*` and `/ws/*` from the frontend origin to
FastAPI and configure authentication and WebSocket origin handling before
allowing remote users. The Vite development proxy is only for local use. The
Lovable source's browser speech recognition and local demo scoring are not used
by the live interview route.
