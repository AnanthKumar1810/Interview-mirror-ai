# InterviewMirror AI — Gnani-aligned scope and evidence

Updated: 9 Nov 2026. This is an implementation ledger, not a claim of live production readiness.

## Feature selection from the AI Voice Agents / LLM Evaluation intern job posting

| Capability | Fit for Gnani challenge | Implementation status |
|---|---|---|
| Structured interview question flow, adaptive follow-ups | High | Existing 3-turn state machine + curated follow-ups; offline tests |
| Prisma speech-to-text and Timbre voice response | Essential | Sync & async provider adapters; mocked transport tests; live credentials unverified |
| English, Telugu, Hindi practice | High | Question prompts and interface; genuine audio-language accuracy unmeasured |
| Noisy telephone speech | High | Added 8/16 kHz PCM ingest, 8->16 kHz resampling, opt-in spectral noise gating; optional DeepFilterNet3 adapter (unverified) |
| Baseline-vs-improved score evaluation | High | v2 vs risk-aware v3 comparison in reports/robust_comparison.json |
| Golden sets, human MAE, rank correlation | High but currently blocked | Existing 9-case *synthetic, unreviewed* corpus; NO gold human scores, so accuracy metrics unavailable |
| Score-stability, dimension drift, CI regression | High | Existing harness + new v3 baseline, synthetic risk gate and GitHub Actions |
| Incorrect/unsupported technical claims | High | Rule-based conservative flags + optional quote-grounded Ollama risk review; NOT a factual oracle |
| STT/LLM/TTS latency measurements | High | Existing async pipeline per-stage timings and timeout tests; added real ASR A/B timing harness |
| Monetary cost instrumentation | Medium | Counts provider calls in A/B; actual provider prices not asserted or computed |
| LiveKit full-duplex / WebRTC agent | Lower for near-term Gnani submission | Deliberately excluded; current app is batch turn-based |
| Provider comparisons and fine-tuning | Lower short-term priority | Not implemented; no evidence they improve results for this demo |

## Result from original synthetic dataset

- 9 synthetic cases, none with human-reviewed reference scores.
- 2 developer-defined risk probes: keyword-stuffing and unsupported perfect-accuracy claim.
- High-scoring risk probes (>=70): baseline 1/2, improved 0/2.
- Cases are small and inspected; **this is not unbiased generalization evidence**.
- Deterministic repeated-score standard deviation is 0, which is *repeatability*, not calibrated correctness.
- Separate diagnostic development and holdout IDs are declared but not a truly blinded test set.

## Recommended next real-world benchmark

1. Collect 20–50 **consented**, varied English/Telugu/code-mixed recordings and expert-checked transcripts; include deliberate background noise and 8 kHz telephone audio.
2. Run `python -m eval_harness.asr_ab --manifest path/to/manifest.json --run-live` with Gnani access, comparing raw versus enhancement WER and latency.
3. Obtain independently human-rated interview answers using rubric dimensions, blinded to candidate scores.
4. Perform scorer calibration on development labels, lock a separate unseen test set, and report MAE, rank agreement and false-high rates.
5. Run at least three full voice interviews, including provider failures, pauses, accents and malformed recordings.
6. Only enable default denoising or live semantic scoring after benchmark results justify the latency, cost and error trade-offs.

**Do not portray a configured key, simulated provider tests, or pretrained DeepFilterNet availability as proof of live real-world performance.**
