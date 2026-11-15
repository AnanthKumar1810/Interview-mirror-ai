# ClearView realtime integration — 15 November 2026

## What changed

The ClearView UI was copied from `AnanthKumar1810/clearview-app-preview` commit
`57e0c40bc5c37ce44b92ebac698c776798746df2` into `frontend/`. The original
repo was not changed. The interview route now connects to FastAPI's
`/ws/interview` through Vite's local proxy. Its Start action opens a persistent
WebSocket, prepares audio playback, requests a microphone stream, and sends raw
16 kHz PCM frames from the existing AudioWorklet. The browser renders Prisma
transcript events and backend state transitions. The backend determines the
answer boundary and speaks the next question with Gnani Timbre.

The app uses only Gnani for speech recognition and speech output. The current
key cannot access Evon, so the adaptive follow-up and practice score remain
deterministic backend logic. The active rubric path no longer invokes Ollama
even if `IM_SEMANTIC_JUDGE=ollama` is set. The report page fetches the SQLite
backed `/api/report/{session_id}` result and shows the original transcript,
dimension totals, evidence, and gaps without recalculating a browser score.

The setup UI now lists the three live backend tracks and three-question length.
Its demo browser STT/TTS route and local scoring are no longer used. The live
page asks for microphone permission without leaving Start stuck in a loading
state. A new `require_streaming` handshake option makes this UI fail visibly
if Prisma streaming is unavailable, because the REST fallback would provide
the transcript only after a completed clip.

## Verification

| Check | Observed result | Limit |
| --- | --- | --- |
| Python suite | 236 passed | Provider transport is mocked in unit tests. |
| Frontend type check | Passed | Type validity only. |
| Frontend tests | 6 passed | Protocol state test uses controlled messages. |
| Frontend build | Passed | Does not prove device audio works. |
| Browser | Setup, live question, End, and report rendered through local frontend and backend | Browser microphone permission was pending; no physical speech was tested. |
| Local API proxy | `/api/status` returned `gnani_live: true` through the frontend origin | This flag means a key is configured, not that every provider call succeeded. |
| Real provider one-turn proxy probe | Prisma WebSocket connected; one synthetic spoken answer reached a segment transcript and turn-final transcript; question two entered `asking` with no errors | Speech came from Gnani Timbre, not a candidate or physical microphone. |

The successful proxy probe recorded `session_ack` at 0.05 s, Prisma connected at
1.93 s, question-one listening at 5.48 s, provider speech start at 6.92 s,
first segment transcript at 19.46 s, and question-two asking at 21.00 s.
These timestamps include opening-question playback and answer duration. They
are one observation and are **not** a p50/p95 latency estimate. The 1.54 s
from first transcript to next-question asking is consistent with the configured
1.5 s adaptive pause window.

This provider run did **not** demonstrate word-by-word interim text during
speech. The transport forwards interim Prisma events immediately when
available. The observed provider message was a segment-final transcript near
the end of the spoken answer. We must not claim a live word-by-word transcript
until a real speech test shows it. For this API behavior, the visible transcript
can update by segment rather than by token. A human microphone and speaker
test is still needed for turn cutoff, barge-in, echo handling, and multilingual
speech on the user's device.

## Run

See [`frontend/README.md`](../frontend/README.md). The new frontend is at
`http://127.0.0.1:8082/app/new`; the backend runs on `127.0.0.1:8002`.
The frontend's Vite proxy is for local development. Production requires a
same-origin reverse proxy for `/api` and `/ws`, plus authentication and
provider usage limits before remote access.
