# Live provider smoke results — 15 November 2026

These checks used the local STT/TTS-only Gnani credential. The secret was read locally and was not printed, written to the archive, or sent to the browser. Live requests may consume account credits. They validate only REST provider access and response handling; they do not validate the interview WebSocket or a physical microphone.

## Prisma and noise-path probe

Three Prisma v2.5 REST requests were sent using one synthetic espeak English clip and its clean control. The original reference sentence is synthetic and known from fixture generation. Results are kept in [`reports/live_asr_synthetic_smoke_2026-11-15.json`](../reports/live_asr_synthetic_smoke_2026-11-15.json).

| Input | Path | Result | WER | Provider latency |
|---|---|---|---:|---:|
| 16 kHz, nominal 10 dB noisy espeak | Raw | No transcript returned | N/A | Not recorded in the first failed probe |
| Same noisy clip | Spectral gate | Two transcript words | 1.00 | 5,034.7 ms |
| Clean espeak control | Raw | Two transcript words | 0.9167 | 3,445.1 ms |

This tiny synthetic probe does not establish noise-filter benefit. There is no valid paired WER because the raw noisy arm produced no transcript. The two transcript-bearing results were both very poor. Do not use these results to select noise processing or claim language accuracy.

## Timbre WAV response

Gnani Timbre v2.5 REST accepted a short English request and returned 76,844 bytes. The response used `0xffffffff` as the RIFF and data chunk sizes, a streaming-style sentinel inconsistent with the complete WAV body returned by REST. The local client now finalizes those two size fields from the complete body before validating and returning it. A repeated live call passed the corrected WAV validation: mono, 16-bit, 24 kHz, 38,400 frames (1.6 seconds), 2,206.7 ms call latency. Report: [`reports/live_tts_smoke_2026-11-15.json`](../reports/live_tts_smoke_2026-11-15.json).

Gnani's [TTS REST documentation](https://docs.gnani.ai/api/TTS/tts-inference) specifies a complete binary WAV response. Its [audio format reference](https://docs.gnani.ai/api/TTS/tts-inference) lists WAV/linear PCM as `audio/wav` and accepts 8–48 kHz sample rates. The body-length correction is limited to RIFF/data sentinel fields; malformed or truncated chunks still fail validation.

## Still needed for meaningful validation

- Real, consented paired clean/noisy speech in English, Telugu, and Telugu-English code-mix, with human-checked reference transcripts.
- Live Prisma WebSocket verification and a real browser microphone / answer / automatic next-question test.
- Human-reviewed gold labels and qualified independent reviewers for answer scoring. This key does not expose semantic evaluator or translation access.
