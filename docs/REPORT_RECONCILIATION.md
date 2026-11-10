# Evaluation report reconciliation — 10 November 2026

Three external evaluations informed this update. Their numerical ratings are opinions, not official Gnani judging scores or calibrated measures of interview quality.

| Report | Source it reviewed | Findings against current repository |
| --- | --- | --- |
| Technical Evaluation Report (live-v2) | 15-file `interviewmirror-ai-live-v2` ZIP | Reproduced a keyword-list scoring exploit and a dead Progress review link in that older build. Current repository had repeated-phrase protection, but unique-word lists still needed a safeguard. |
| Gnani internship evaluation (10 Nov) | 65-file `InterviewMirrorAI_Gnani_Upgrade_2026-11-09.zip` | Confirmed offline tests and risk-aware scoring in that archive. Its in-memory-session and unbenchmarked-noise findings predate the 86-file GitHub build, which has SQLite auth and a small synthetic noise benchmark. |
| Senior AI Engineering Evaluation & Technical Audit (provided by user) | `InterviewMirrorAI-Gnani-Upgrade`, version not pinned | Reported silent mock fallbacks, in-memory sessions, open CORS, acoustic pace/pitch scoring and live streaming. The current code has explicit provider errors, SQLite, no CORS wildcard, transcript-only scores, and a recorded-upload REST workflow. Those positive and negative claims must not be carried over as facts. |

## Changes in this update

- Added a conservative flag and score cap for dense, disconnected English keyword lists, including lists without repeated phrases. This is a narrow heuristic; it is not a coherence classifier or proof of correctness. The regression tests cover both a unique-word exploit and a coherent answer.
- Added documented Prisma v2.5 `bias_list` with `bias_score=1.0` for single letter-only words from the selected track. Its effect on word error rate is unmeasured; the UI asks users to review the transcript. The backend validates the track and never takes arbitrary boost terms from the browser.
- Turned Progress review into a functional account-history view. It reads owner-scoped SQLite sessions and reports, showing transcripts and feedback. Account history requires `IM_AUTH_REQUIRED=true` and a configured signing secret.
- Added a visible interview stepper and improved mobile navigation, status text, and contrast on audio controls.

## Open evidence gaps

- No live Prisma or Timbre request was made in this review. A configured API key only indicates availability, not successful authentication or correct audio output.
- No human-rated answer labels exist. Numerical scores should not be used for selection, hiring, language proficiency or factual correctness.
- The available practice review queue has nine synthetic cases, not a representative Hindi/Telugu speech dataset. The separate noise benchmark covers four synthetic paired fixtures and does not demonstrate lower Prisma WER.
- Real multilingual WER, latency, denoising benefit, streaming, and public deployment readiness remain unverified.
- A public demo post and competition submission are user-facing work requiring real credentials, audio, and publication. Do not substitute a mocked demo.

Gnani's [REST STT documentation](https://docs.gnani.ai/api/STT/speech-to-text) defines `bias_list` and positive `bias_score` for Prisma v2.5. It also defines a separate `keyterms` field for Prisma v3.0; this update leaves the existing v2.5 model selection unchanged.
