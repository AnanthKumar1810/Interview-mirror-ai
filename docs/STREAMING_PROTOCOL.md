# InterviewMirror Streaming WebSocket Protocol (v1.0)

## 1. Protocol Overview

The InterviewMirror streaming protocol governs full-duplex communication between the client browser and the FastAPI backend over WebSocket at `/ws/interview`.

### General Constraints
- **Protocol Version**: `"1.0"` (validated on connect via query parameter `?protocol_version=1.0` and inside JSON control frames).
- **Control Transport**: UTF-8 encoded JSON text frames.
- **Audio Transport**: Raw binary PCM frames (1,024 bytes / 512 samples at 16 kHz mono signed 16-bit LE).
- **Bounds**:
  - Maximum queue depth: `256` items.
  - Maximum session duration: `600` seconds (`MAX_SESSION_DURATION_S`).
  - Sequence number wrap-around: $2^{32}$ (`4,294,967,296`).
  - Client pause threshold for turn completion: `1.8` seconds (`ANSWER_PAUSE_TIMEOUT_S`).
  - Candidate hesitation reprompt: `15.0` seconds (`NO_SPEECH_REPROMPT_S`).

---

## 2. Binary Audio Frame Specification

Audio frames stream continuously from the client's `AudioWorklet` to the server.

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Sample Rate** | 16,000 Hz | Resampled client-side by AudioWorklet |
| **Channels** | 1 (Mono) | Channel 0 of microphone |
| **Bit Depth** | 16-bit | Signed integer (`Int16LE`) |
| **Endianness** | Little-Endian | Standard PCM representation |
| **Frame Size (Samples)** | 512 samples | Exactly 32ms per frame |
| **Frame Size (Bytes)** | 1,024 bytes | `512 samples * 2 bytes/sample` |
| **Cadence** | 32 ms | Steady streaming; no burst buffering |

Frames that do not match `1024` bytes are identified via `is_pcm_frame()` and treated as malformed.

---

## 3. Sequence Numbering and Header Envelope

All JSON control messages inherit from the base protocol schema:

```json
{
  "type": "<message_type>",
  "protocol_version": "1.0",
  "sequence_number": 42,
  "turn_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "timestamp_ms": 1731510000000
}
```

### Sequence Number Rules
1. Server increments `sequence_number` monotonically for each outgoing control frame.
2. When the counter reaches $2^{32} - 1$, the subsequent value wraps around to `0` using modular arithmetic:
   $$\text{next\_seq} = (\text{current\_seq} + 1) \pmod{2^{32}}$$
3. Missing or out-of-order sequence numbers indicate network packet drop or queue shedding.

---

## 4. Control Message Reference

### 4.1 Client → Server Messages

#### `session_start`
Initiates a hands-free interview session.
```json
{
  "type": "session_start",
  "protocol_version": "1.0",
  "sequence_number": 0,
  "turn_id": "uuid-v4",
  "timestamp_ms": 1731510000000,
  "track": "agentic",
  "language": "en-IN",
  "consent_given": true,
  "stt_model": "prisma-v2.5",
  "token": "eyJhbGciOi...",
  "endpointing_policy": "adaptive"
}
```

#### `playback_start`
Client notifies the server when audible TTS playback begins on the browser AudioContext timeline.
```json
{
  "type": "playback_start",
  "generation_id": 1,
  "client_timestamp_ms": 1731510002100
}
```

#### `playback_stop`
Client notifies the server when audible TTS playback ceases (either all audio buffers completed or interrupted).
```json
{
  "type": "playback_stop",
  "generation_id": 1,
  "client_timestamp_ms": 1731510006300
}
```

#### `barge_in`
Emitted immediately when client-side debounced VAD (3 consecutive frames / ~96ms above adaptive noise floor) detects candidate speech while interviewer TTS is active.
```json
{
  "type": "barge_in",
  "turn_id": "uuid-v4",
  "generation_id": 2,
  "timestamp_ms": 1731510003500
}
```

#### `end_audio`
Optional signal when microphone stream ends or pause is detected client-side.
```json
{
  "type": "end_audio",
  "turn_id": "uuid-v4",
  "timestamp_ms": 1731510005000
}
```

#### `end_interview`
Candidate requests early termination of the interview session.
```json
{
  "type": "end_interview",
  "turn_id": "uuid-v4",
  "timestamp_ms": 1731510012000
}
```

#### `ping`
Heartbeat keepalive.
```json
{
  "type": "ping",
  "turn_id": "uuid-v4",
  "timestamp_ms": 1731510010000
}
```

---

### 4.2 Server → Client Messages

#### `session_ack`
Confirms session initialization with authoritative session ID.
```json
{
  "type": "session_ack",
  "session_id": "3f4c6e91-c918-4e89-8d72-96db1a03f421",
  "status": "ok",
  "question": "Can you walk through how you built your agentic pipeline?",
  "question_number": 1,
  "total_questions": 3
}
```

#### `turn_state`
Indicates current state transition (`asking`, `listening`, `transcribing`, `review`, `feedback`, `followup`, `completed`).
```json
{
  "type": "turn_state",
  "state": "asking",
  "question": "Can you walk through how you built your agentic pipeline?",
  "question_number": 1,
  "feedback": null
}
```

#### `tts_audio_meta`
Precedes binary TTS audio stream chunks.
```json
{
  "type": "tts_audio_meta",
  "voice": "Pranav",
  "language": "en-IN",
  "duration_ms": 3200.0,
  "size_bytes": 102400
}
```

#### `transcript`
Delivers real-time intermediate or final transcribed text.
```json
{
  "type": "transcript",
  "text": "I used Python with async queues to coordinate the workers.",
  "is_final": true,
  "source": "gnani_prisma",
  "provider_latency_ms": 184.5
}
```

#### `reprompt`
Dispatched when candidate hesitates for 15s without speaking.
```json
{
  "type": "reprompt",
  "message": "Take your time. When you are ready, share your experience.",
  "question_number": 1
}
```

#### `metrics`
Session telemetry and nearest-rank percentiles emitted at completion or teardown.
```json
{
  "type": "metrics",
  "data": {
    "session_duration_s": 145.2,
    "connection_successes": 1,
    "connection_failures": 0,
    "dropped_frames": 0,
    "latencies": {
      "end_of_speech_to_transcript": {"p50_ms": 185.0, "p95_ms": 320.0},
      "transcript_to_first_audio": {"p50_ms": 160.0, "p95_ms": 290.0},
      "end_of_speech_to_playback": {"p50_ms": 2167.0, "p95_ms": 2445.0}
    },
    "note": "Latency includes conversational silence pause window (1.2–1.8s) required for turn detection."
  }
}
```

---

## 5. Gnani Streaming Wire Contract

### Upstream Prisma STT (`wss://api.vachana.ai/stt/v3/stream`)
- **Headers**:
  ```http
  X-API-Key-ID: <GNANI_API_KEY>
  language_code: en-IN
  model: prisma-v2.5
  format: transcribe
  sample_rate: 16000
  encoding: pcm_s16le
  ```
- **Audio Framing**: Raw binary PCM frames of 1,024 bytes.
- **Explicit Flush**: `{"type": "commit"}` sent when candidate pause timeout expires.
- **Events**: Receives JSON events (`speech_start`, `final`, etc.) and yields final transcripts.

### Upstream Timbre TTS (`wss://api.vachana.ai/api/v1/tts`)
- **Synthesis Request**:
  ```json
  {
    "text": "Can you explain how you designed your system?",
    "voice": "Pranav",
    "language": "en-IN",
    "model": "timbre-v2.5"
  }
  ```
- **Audio Payload**: Chunks arrive as base64-encoded PCM inside JSON messages, concluded with `type="complete"`.
- **Cancellation**: Task cancellation stops streaming immediately upon barge-in without sending undocumented interruption messages.

---

## 6. Post-Interview Transcript Correction Endpoint

- **Endpoint**: `POST /api/sessions/{session_id}/correct`
- **Request Payload**:
  ```json
  {
    "turn_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "corrected_text": "I used Python with asyncio and queues."
  }
  ```
- **Response**:
  ```json
  {
    "status": "corrected",
    "turn_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "provider_transcript": "I used Python with async you and queues.",
    "edited_transcript": "I used Python with asyncio and queues.",
    "new_score": 78,
    "feedback": { ... }
  }
  ```
- Preserves the raw provider transcript for audit integrity while updating session score based on user-verified wording.
