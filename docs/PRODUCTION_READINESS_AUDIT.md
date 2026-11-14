# PRODUCTION READINESS AUDIT & DEFECT INVENTORY — PLAN X+ V3
**Document ID:** `docs/PRODUCTION_READINESS_AUDIT.md`  
**System:** InterviewMirror AI (Hands-Free Multilingual Technical Interview Practice Platform)  
**Baseline Git Commit:** `2e23ced`  
**Development Branch:** `codex/plan-x-plus-v3-production`  
**Date:** November 14, 2026  
**Auditor:** Principal AI Systems Architect & QA Lead  

---

## 1. Executive Summary & Verification Baseline

This audit evaluates the InterviewMirror AI platform at baseline commit `2e23ced` following the Plan X+ V2 milestone. The automated regression suite comprises **218 passing tests** across 28 test files in Python 3.13. 

While the fundamental WebSocket streaming transport, AudioWorklet microphone acquisition, barge-in cancellation, and 4-dimension practice rubric are verified in simulated unit/integration tests, critical production hardening gaps remain before multi-tenant and scaled real-world deployment:

1. **Live Upstream Gnani Verification**: The upstream connection to `api.vachana.ai` remains **BLOCKED** in automated CI due to unavailable server credentials. Independent mock contracts are fully passing.
2. **Conversational Intelligence**: Follow-up question selection currently relies on a static 3-tier matrix without a structured candidate knowledge model, concept graph traversal, or conversational dialogue policy (handling user clarification requests, repetitions, skips, or admissions of uncertainty).
3. **Turn Idempotency & Reconnection**: Turn commitment in the WebSocket router relies primarily on an in-memory `asyncio.Lock`. A network reconnect or duplicate client frame can cause state divergence if the connection is dropped and resumed.
4. **Append-Only Audit Trail**: SQLite database currently stores only final and in-progress session snapshots in `interviews.state_json`, lacking an append-only `session_events` ledger for reproducible turn-by-turn trace auditability.
5. **Multilingual Technical Term Normalization**: Technical loanwords (e.g., Docker, FastAPI, asyncio, Kubernetes) in Telugu and Hindi require script-tolerant matching and tracking to distinguish ASR phonetic variance from genuine candidate misunderstanding.

---

## 2. Component-by-Component Architecture Audit

| Component | Files | Current Status | Production Readiness Assessment |
| :--- | :--- | :--- | :--- |
| **WebSocket Transport** | `ws_router.py`, `ws_protocol.py` | Partially Verified | Robust async decoupling with supervised tasks; lacks explicit reconnect resume handshake and persistent turn idempotency key. |
| **Speech-to-Text (STT)** | `gnani_streaming.py`, `gnani.py` | Verified (Simulated) / Blocked (Live) | Handles binary streaming, Prisma upgrade headers, VAD events. Verified against mocks. Upstream live verification blocked by missing API key. |
| **Text-to-Speech (TTS)** | `gnani_streaming.py`, `ws_router.py` | Verified (Simulated) / Blocked (Live) | Decoupled `_dispatch_tts` runner with `generation_id` cancellation on barge-in. Live audio verified against mocks. |
| **Browser Mic & Audio** | `static/audio-worklet.js`, `static/realtime-client.js` | Operational | Windowed sinc FIR anti-aliasing resampling (Hann window, 7.2kHz cutoff) to 16kHz PCM16. Adaptive barge-in threshold. |
| **Interview State Machine** | `interview_state.py` | Operational | Deterministic 8-state machine. Hardcoded to 3 questions; lacks dynamic dialogue policy (clarification, repetition, skip). |
| **Adaptive Questioning** | `adaptive.py`, `coach.py` | Operational | 3 difficulty tiers (fundamentals, applied, architecture) with misconception grounding. Lacks structured competency graph. |
| **Evaluation Rubric** | `robust_evaluation.py`, `evaluation.py` | Operational | 4-dimension practice rubric (30% tech, 25% trade-off, 25% evidence, 20% clarity) with anti-stuffing bounds and verbatim quote extraction. |
| **Personalization** | `personalization.py` | Operational | Safe resume parsing (bounded to 50k chars) and read-only GitHub repository inspector with SSRF protection. |
| **Persistence & DB** | `storage.py` | Operational | SQLite WAL with optimistic concurrency (`version`), user auth, and token revocation. Schema version 1; lacks `session_events`. |
| **Telemetry & Metrics** | `metrics.py`, `ws_router.py` | Operational | Monotonic server-side timestamps, browser playback telemetry aggregation, SQLite store counter aggregation. |
| **Security & Auth** | `auth_service.py`, `main.py` | Operational | PBKDF2 password hashing, short-lived JWT tokens, WebSocket handshake validation, cross-user session hijacking prevention. |

---

## 3. Production Risk Matrix & Defect Inventory

The following defects and architectural requirements are classified by severity:

### Priority P0: Critical Security, Integrity, or Core Interaction Defects

#### DEF-01: Persistent Turn Idempotency Gap Across WebSocket Reconnects
- **Affected File:** `ws_router.py`, `interview_state.py`, `storage.py`
- **Root Cause:** Turn finalization relies on an in-memory `asyncio.Lock` and session versioning in `storage.py`. If a WebSocket drops mid-turn and the client reconnects or retransmits, or if concurrent client frames arrive, the state machine can attempt duplicate transitions or drop accumulated turns.
- **User Impact:** Answer might be scored twice, or next question skipped, resulting in corrupted candidate session reports.
- **Proposed Repair:** Introduce unique persistent `turn_id` with an explicit idempotent check: if `turn_id` is already committed in `session.answers`, return the existing evaluation rather than re-advancing. Add session resume capability to `/ws/interview`.
- **Required Tests:** Test concurrent/repeated finalize calls with same `turn_id`, reconnect during active listening state.
- **Acceptance Criteria:** Exactly-once commitment per turn ID under simulated network reconnects and packet re-deliveries.

#### DEF-02: Missing Append-Only Event Audit Trail
- **Affected File:** `storage.py`, `ws_router.py`
- **Root Cause:** Session state updates overwrite the single `interviews.state_json` column. If a worker crashes or an evaluation anomaly occurs, the temporal history of events (speech_start, pause_expired, tts_dispatched, barge_in) is lost.
- **User Impact:** Inability to debug latency regressions, false interruptions, or candidate disputes regarding speech recognition.
- **Proposed Repair:** Perform SQLite schema migration from `user_version = 1` to `user_version = 2`. Add `session_events` table (`event_id`, `session_id`, `trace_id`, `event_type`, `timestamp`, `payload_json`).
- **Required Tests:** Schema migration test, event insertion test, event retrieval test.
- **Acceptance Criteria:** All significant interview state transitions and provider events are logged to `session_events`.

---

### Priority P1: Reliability, Intelligence & Multilingual Correctness Deficiencies

#### DEF-03: Lack of Conversational Dialogue Policy (Clarifications, Repetitions, Skips, Uncertainty)
- **Affected File:** `interview_state.py`, `adaptive.py`, `ws_router.py`
- **Root Cause:** Every finalized candidate utterance is unconditionally treated as an answer and evaluated against the question rubric. If a candidate says *"Could you please explain the question?"*, *"Can you repeat that?"*, *"I don't know the answer"*, or *"Let's skip this question"*, the system penalizes them with a low technical score and advances.
- **User Impact:** Hostile, unnatural interview experience that punishes candidates for natural conversational interactions.
- **Proposed Repair:** Implement an explicit `DialoguePolicy` that detects conversational intents (`clarification`, `repeat`, `uncertainty`, `skip`, `answer`).
  - *Clarification:* Explain/rephrase question, remain on current turn, zero penalty.
  - *Repeat:* Re-synthesize question, remain on current turn.
  - *Uncertainty:* Acknowledge uncertainty, de-escalate to foundational concept, provide coaching hint.
  - *Skip:* Record question as skipped, move cleanly to next topic without corrupting rubric.
- **Required Tests:** Test clarification intent handling, repeat intent, uncertainty detection, skip progression.
- **Acceptance Criteria:** Clarifications and repeats do not advance question index or lower score.

#### DEF-04: Lack of Structured Candidate Knowledge Model & Competency Graph
- **Affected File:** `adaptive.py`, `interview_state.py`
- **Root Cause:** Question selection chooses between 3 tiers using only the previous answer's aggregate score, leading to potential topic incoherence or abrupt conceptual jumps.
- **User Impact:** Interview questions feel disconnected from earlier answers.
- **Proposed Repair:** Build a `CandidateKnowledgeModel` tracking competencies (`status`: demonstrated, partially_demonstrated, missing, misconception), and a `CompetencyGraph` defining concept prerequisites and related follow-ups for each track (e.g. `software`, `agentic`, `ai`).
- **Required Tests:** Test knowledge model state updates, graph-guided follow-up selection, and repetition avoidance.
- **Acceptance Criteria:** Follow-up questions explicitly target concepts adjacent to demonstrated or missing concepts in the competency graph.

#### DEF-05: Multilingual Technical Term Misalignment & Script Normalization
- **Affected File:** `evaluation.py`, `eval_harness/datasets/practice_review_queue.json`
- **Root Cause:** In Telugu and Hindi interviews, Prisma STT frequently outputs English technical terms in Latin script or transliterated Indic script. Exact word matching causes false negatives.
- **User Impact:** Candidates speaking Telugu or Hindi are penalized on technical accuracy even when pronouncing correct concepts.
- **Proposed Repair:** Expand multilingual synonym and script mappings in `evaluation.py` and `adaptive.py` for core technical vocabulary (FastAPI, Redis, PostgreSQL, Docker, Kubernetes, asyncio, coroutines, etc.).
- **Required Tests:** Multilingual evaluation fidelity test comparing Latin and Indic representations of technical concepts.
- **Acceptance Criteria:** Equal or higher technical concept recall on code-mixed and transliterated answers.

---

### Priority P2: Advanced Product Capabilities & Personalization

#### DEF-06: Static 3-Question Session Constraint
- **Affected File:** `interview_state.py`, `main.py`, `ws_router.py`
- **Root Cause:** Session length is hardcoded to `MAX_QUESTIONS = 3`.
- **User Impact:** Candidates cannot choose a 5-question or 10-question practice session.
- **Proposed Repair:** Support configurable session length (`target_questions` = 3, 5, or 7) in `InterviewStateMachine`, defaulting to 3 for backward compatibility.
- **Required Tests:** Verify completion logic for 3, 5, and custom length sessions.
- **Acceptance Criteria:** State machine completes only after configured number of substantive answers.

#### DEF-07: Personalized Resume & GitHub Topic Seeding Integration
- **Affected File:** `personalization.py`, `interview_state.py`, `ws_router.py`
- **Root Cause:** `personalization.py` can parse resumes and inspect GitHub repos, but the extracted skills are not automatically injected into the active `InterviewStateMachine` seed context.
- **User Impact:** Candidates who submit a resume still receive the default generic track opening question.
- **Proposed Repair:** Wire candidate profile and extracted skills from `personalization.py` directly into `InterviewStateMachine` initialization to select tailored opening questions.
- **Required Tests:** Test question personalization from resume profile.
- **Acceptance Criteria:** Candidate with FastAPI/PostgreSQL background receives questions seeded with those technologies.

---

### Priority P3: Observability & Operational Optimization

#### DEF-08: Telemetry Clock Synchronization & Precision Tracking
- **Affected File:** `metrics.py`, `ws_router.py`
- **Root Cause:** Telemetry combines client timestamps with server monotonic clocks without distinguishing local clock drift from end-to-end transport latency.
- **User Impact:** Browser playback latency percentiles may show negative or inflated values if client system clock is skewed.
- **Proposed Repair:** Clearly separate browser-reported delta measurements (`browser_playback_latency_ms`) from server-measured monotonic intervals (`server_processing_ms`).
- **Required Tests:** Test metrics calculation with simulated clock skew.
- **Acceptance Criteria:** No negative latencies in summary metrics; explicit separation of server vs client telemetry.

---

## 4. Release Checkpoint & Rollback Strategy

- **Baseline Commit:** `2e23ced`
- **Development Branch:** `codex/plan-x-plus-v3-production`
- **Rollback Command:**  
  ```bash
  git checkout codex/plan-x-plus-advancement
  ```
- **Database Safety:** SQLite database migrations are strictly additive. Database version 2 introduces `session_events` without dropping existing tables or modifying existing columns.
