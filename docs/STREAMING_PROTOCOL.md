# Browser WebSocket protocol v1.0

Endpoint: `/ws/interview?protocol_version=1.0`. The server accepts only local connections by default and checks the browser Origin against Host. The first JSON text message must be `session_start` with `track`, `language`, `stt_model`, and `consent_given: true`. The server replies with `session_ack`. The REST session remains authoritative for the current question; do not use the acknowledgment's question for later turns.

The browser sends signed 16-bit little-endian, mono, 16 kHz PCM in **exactly 1,024-byte** binary frames (32 ms). Other sizes receive `invalid_audio_frame`. It sends `{"type":"end_audio"}` when recording stops; the server translates this to Gnani's `{"type":"commit"}` control frame. Prisma may also finalize an utterance using server-side VAD. Final transcripts are forwarded as `{"type":"transcript","text":"...","is_final":true}` and the candidate may edit them before `/api/answer`.

`ping` receives `pong`. `provider_event` carries connection, speech and error status; `turn_state` reaches `review` after a final transcript. `metrics` is emitted on connection teardown. Outgoing messages include protocol version, sequence number, turn ID and timestamp. Binary TTS frames and `tts_audio_meta` are reserved for a future unified interview route; this route currently streams STT only.

See the [Prisma](https://docs.gnani.ai/api/STT/stt-websocket) and [Timbre](https://docs.gnani.ai/api/TTS/tts-websocket) official protocols for upstream details. Provider JSON is translated by `gnani_streaming.py`; it is not passed through verbatim to the browser.
