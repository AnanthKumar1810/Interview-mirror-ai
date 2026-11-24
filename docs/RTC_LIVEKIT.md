# Optional LiveKit RTC interview

The default browser microphone path remains `/ws/interview` through FastAPI and
Gnani. The **LiveKit WebRTC (experimental)** choice uses a real LiveKit room with
an agent worker. It uses the same SQLite sessions, authored questions,
deterministic answer evaluation and report endpoint. No Evon or hosted LLM is
added. Audio goes from the browser over WebRTC to LiveKit and from the worker
to Gnani Prisma; Timbre produces the interviewer speech. The Gnani key stays
on the server.

## Setup

1. Install `requirements-livekit.txt` in the backend environment and run
   `npm ci` in `frontend/` (the browser SDK is pinned in its lockfile).
2. Provision a LiveKit Cloud or self-hosted server. In a local, untracked
   `.env`, set `IM_LIVEKIT_ENABLED=true`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
   `LIVEKIT_API_SECRET`, and `GNANI_API_KEY`. Use `wss://` for a public browser
   deployment. In production, set `IM_ENV=production`, `IM_AUTH_REQUIRED=true`
   and a strong `IM_JWT_SECRET`, and apply proxy-level rate limits. The room
   token is scoped to one room and expires after 30 minutes.
3. In one process start FastAPI as usual. In a second process run
   `python rtc_agent.py download-files` once to obtain the local turn detector
   assets, then `python rtc_agent.py dev` for local use or
   `python rtc_agent.py start` for deployment. The worker and FastAPI process
   must share the same database path or a shared database. SQLite on separate
   machines is not supported by this configuration.
4. Run the frontend and select **LiveKit WebRTC (experimental)** in the Format
   step. This path currently supports the existing three-question report.

The token endpoint is `POST /api/rtc/session`. It creates the interview, a
two-participant room and an explicit dispatch for the named worker
`interview-mirror`. It never returns either provider secret. The worker checks
room identity and uses the dispatch metadata to load the owner-scoped session.
Once the candidate leaves, the worker closes the agent session and invalidates
pending output. For public hosting, the existing bearer authentication must
be wired into the frontend if authentication is enabled; the current UI starts
anonymous demo interviews only.

## Turn handling and language support

- Gnani's official LiveKit `STT` streams Prisma over WebSocket at 16 kHz.
  Its `TTS` uses Timbre v2.5 and the documented WebSocket synthesis mode.
  The worker uses the repo's existing language-to-voice map.
- Silero VAD runs locally for speech activity and interruptions. The local
  LiveKit `MultilingualModel` semantic end-of-turn detector is selected for
  English and Hindi. [LiveKit's supported-language list](https://docs.livekit.io/agents/logic/turns/turn-detector/)
  includes those languages, but **not Telugu**. Telugu uses VAD-only end-of-turn
  detection with configured endpointing delays; it is not described as
  semantically detected.
- LiveKit's adaptive interruption model is optional and disabled by default.
  Set `IM_RTC_ADAPTIVE_INTERRUPTION=true` only with a LiveKit project that
  supports the model and after accepting that this adds LiveKit model-service
  processing. Otherwise VAD interruption remains in use. The official model
  can treat brief acknowledgments as backchannels. The local backchannel
  policy also discards short acknowledgments while the agent is speaking.
- LiveKit owns active speech playback and interrupts the TTS SpeechHandle.
  The app's turn ledger rejects duplicate or stale question events and
  invalidates output on cancellation and room teardown. This is not a measured
  claim about acoustic interruption latency.

## Reproducible live smoke test

With the above credentials, provider entitlement, a running worker, and an
actual microphone and speaker:

1. Start a three-question English RTC session. In browser developer tools,
   verify the room connects via WebRTC, one microphone track is published,
   and a remote agent audio track is subscribed. Confirm the first question
   is audible and the control channel shows `session_ack`.
2. Answer all three questions. Verify final transcripts, the next question,
   a report at `/api/report/{session_id}`, and one saved answer per turn.
3. During a spoken question, say “okay” briefly, then try a clear interruption
   such as “please repeat the question.” Check whether playback continues for
   the acknowledgment and stops for the interruption in the chosen mode.
4. Repeat in Hindi and Telugu. Expect semantic endpointing only for Hindi;
   verify Telugu VAD still completes a turn after a pause. Leave the room
   during Timbre playback and check that no late audio or answer appears.
5. Repeat with the default **Standard voice** choice to confirm the FastAPI
   WebSocket path still works. Record browser, worker and provider observations
   separately; avoid presenting a synthetic transcript as a live result.

Offline tests and a browser build verify code paths, not Gnani authentication,
an active LiveKit worker, a physical device, latency or real audio behavior.

## RTC turn-taking lab

The optional worker records overlapping user/agent speech state until the
final transcript, ignores short acknowledgments while speaking, accepts short
answers, and replays a pending question when asked to repeat. If VAD already
stopped a question on a backchannel, it restarts the question from the beginning.
The worker may cancel a still-active SpeechHandle on a substantive interruption.
VAD false-interruption recovery is configured for 1.2 seconds. Aggregate-only
callback timing and counts are saved to .data/rtc-turn-lab/. These are not
microphone-to-speaker latency. See docs/RTC_TURN_TAKING_LAB.md.
