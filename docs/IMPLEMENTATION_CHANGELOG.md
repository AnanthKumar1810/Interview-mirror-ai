# Implementation changelog — 9 November 2026

All enhancements are applied to the prior `InterviewMirrorAI_Phase2_AsyncVoice_Ready.zip` source archive; the user’s local Windows checkout was not overwritten.

- Introduced `robust_evaluation.py` for conservative, explicitly unvalidated risk-aware scoring.
- Added exact-quote validation for optional model-generated correctness-risk signals (`semantic_judge.py`).
- Preserved original v2 scorer for reproducible baseline comparison.
- Added deterministic scoring comparison, declared diagnostic splits and adversarial CI gate (`eval_harness/compare_robust.py`).
- Added `speech_enhancement.py` (raw, portable spectral gate and optional, separately installed DeepFilterNet3) for 8/16-kHz WAV input and 16-kHz STT output.
- Added live, explicit-consent raw-vs-enhanced ASR WER benchmark tool (no actual calls performed here).
- Improved frontend with noise-choice UI, consent checkbox and risk-warning display.
- Required consent at backend Gnani STT entry points, including compatibility routes; added per-process provider budget.
- Added short-lived in-memory session TTL, deletion endpoint and HTTP security headers.
- Added tests for risk controls, preserved strong/Telugu cases, quoted semantic signals, noise processing, HTTP contracts, consent and WER.
- Added Dockerfile, GitHub Actions gates, runbook and production-readiness blockers.

## Out of scope and unverified
- No human scoring labels, so scorer MAE or ranking agreement with humans cannot be reported.
- No user Gnani API key, so no authenticated live Prisma/Timbre requests have been executed here.
- No consented corpus of telephone recordings, so no claim of reduced WER or noisy real-world reliability.
- No deployed production service, OIDC authentication, durable database, multi-tenant limits, or independent security validation.
