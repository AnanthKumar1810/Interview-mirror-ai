# First-answer handoff: investigation and fix (2026-11-14)

## Scope and evidence

This report covers the user-supplied `InterviewMirror-AI-realtime-voice 2.0.zip`. Source code and executable tests are the implementation evidence. The attached development reports are historical claims. The separate “Analyse Blueprint Architecture” chat describes the product goal: a natural spoken interview with no recording controls after Start.

The supplied ZIP had no `.env`, API key, or SQLite database. The private key was read from the user's local `api.env.txt` for short live probes and was not copied into this project, logs, or output archives.

## Reproduced failure

Both streaming adapters sent `x-api-key-id` and `X-API-Key-ID` in the same connection. HTTP header names are case-insensitive, so this is a duplicate authentication header. With the supplied valid key, the ZIP's Timbre WebSocket adapter received **HTTP 401**. A handshake-only probe using one header connected to **both** Gnani streaming endpoints. Removing the duplicate allowed a real Timbre synthesis and Prisma transcript.

Gnani's [Prisma streaming documentation](https://docs.gnani.ai/api/STT/stt-websocket) lists `processing` and segment-final `transcript` messages but no guaranteed `speech_end` message. A real trace observed `connected`, `speech_start`, and `transcript` with `is_final=true`; no `speech_end` arrived. The code now finalizes from the segment-final transcript after its configured candidate-pause window. It deduplicates segment IDs and no longer sends an extra `commit` when an already-final segment's pause timer expires.

## Other corrections

- The REST fallback no longer invents a candidate answer when STT returns no transcript. It returns an error and lets the candidate retry.
- The browser waits for `session_ack` before starting microphone capture. Its connection failure and timeout are reported.
- A `tts_complete` control message is ordered after the audio chunks. The browser keeps question playback running through the final scheduled chunk; a `listening` state message no longer cuts it off. Microphone audio is withheld from Prisma while the browser reports question playback, unless the candidate barges in.
- Browser playback is prepared during the Start click to respect autoplay restrictions. Audio uses the sample rate in TTS metadata.
- Candidate transcripts and personalization fields are rendered as text rather than interpolated into HTML.
- WebSocket origin checks and local-only defaults protect an unauthenticated deployment; remote streaming requires authentication or an explicit opt-in environment setting. Credentials are no longer placed in the browser WebSocket URL.
- Recoverable Prisma error messages no longer terminate the event reader. Invalid audio frame sizes are rejected.

## Verification

| Check | Result | Limit |
| --- | --- | --- |
| Original ZIP offline suite | 233 passed | Provider transports mocked |
| Corrected offline suite | 235 passed | Two additional first-turn regressions |
| Browser JavaScript syntax | Both scripts passed `node --check` | No physical microphone or speaker check |
| Live Gnani adapter probe | Timbre generated 16 kHz audio; Prisma returned an 86-character final transcript | One synthetic spoken answer |
| Live local interview WebSocket | First answer produced final transcript, `transcribing`, `review`, `feedback`, `followup`, and question-two `asking`; question-two TTS audio bytes arrived | Synthetic audio sent through a WebSocket client, not a human browser microphone |

The live interview trace observed question-one `listening` at 5.645 s, first final transcript at 15.320 s, question-two `asking` at 16.851 s, and question-two audio delivery shortly after. These timestamps include the generated answer's audio duration and provider processing; they do not establish p50/p95 or a 400–600 ms turnaround.

## Remaining work

Test a full interview through an actual browser microphone and speaker. Validate playback completion, barge-in, reconnect, and multilingual recognition under real device and network conditions. Establish repeated latency distributions and human-reviewed cutoff accuracy. The current key provides Gnani STT/TTS only, so the practice rubric and follow-up policy remain deterministic; this is not Gnani Evon semantic evaluation. Do not call this build production ready until those checks and public deployment authentication/rate limits are complete.
