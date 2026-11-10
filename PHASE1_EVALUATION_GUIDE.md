# Phase 1: Interview scoring evaluation — engineering preparation

## Actual baseline

InterviewMirror's current **numeric** scorer is `evaluation.evaluate_answer`, a deterministic term-coverage and structural-evidence heuristic. The `coach.ollama_refine` integration may add **qualitative** feedback when `OLLAMA_MODEL` is configured, but it does not independently score or verify factual correctness.

**What was implemented in this phase:**

- A reusable `eval_harness` for 0–100 scoring with dimension caps 25/35/20/20.
- A synthetic, multilingual **review queue** of 9 examples (English, Telugu, Hindi), including adversarial keyword stuffing and implausible claims.
- Five repeat executions per case, with per-case score/dimension means and population standard deviation; local scoring call latency mean and nearest-rank p95.
- A dataset SHA-256 fingerprint and a snapshot regression gate that checks **both overall scores and dimension scores**, even when the total is unchanged.
- A guarded, *optional* experimental **Ollama numerical judge**; temperature 0, structured JSON, limits validation, no silent fallback. This is separate from production `coach.ollama_refine` and is **not** validated or enabled in the user-facing app.
- Tests for instability, invalid scores, baseline changes, omitted human labels, score conservation, and a simulated Ollama provider.
- GitHub Actions gate on both Python 3.11 and 3.13. No real Gnani or Ollama calls in CI.

## Commands

From the project root (after installing `requirements-dev.txt`):

```bash
python -m pytest -q
python -m eval_harness.run --dataset eval_harness/datasets/practice_review_queue.json --repeats 5 --output reports/phase1_latest.json --compare reports/phase1_baseline.json --max-absolute-score-drift 0 --max-within-case-std 0
```

If a rubric change intentionally changes scores, **do not quietly overwrite the baseline**. First inspect the difference and obtain/verify human-reviewed labels. Then update `reports/phase1_baseline.json` intentionally with the approved scorer version and commit the accompanying explanation.

To experiment with a numerical local LLM evaluator, with Ollama running on your machine:

```powershell
$env:OLLAMA_MODEL = "qwen2.5-coder:7b" # Or another locally installed model
python -m eval_harness.run --scorer ollama --repeats 3 --output reports/phase1_ollama_experiment.json
```

The experimental numerical judge's output is **not** silently substituted into the FastAPI app. A local model may return invalid JSON, time out, or produce unstable/inaccurate scores. Those are meaningful failures; preserve them. Ollama calls can be costly/slow and require the service/model to be installed. This command has not been run against the live model in this archive's verification environment.

## Current representative results

From `reports/phase1_baseline.json` (`transcript_heuristic_v2`):

| Synthetic case | Score /100 | What this illustrates |
|---|---:|---|
| `agentic_en_strong` | 93 | Detailed technical terms and evidence receive a high score |
| `agentic_en_empty` | 2 | Unrelated response is scored low |
| `agentic_en_keyword_stuffing` | 63 | **Failure:** repeating concepts can earn substantial points |
| `ai_en_false_claim` | 82 | **Failure:** false assurance of 100% error-free future predictions earns a high score |

There are **9 cases × 5 repeats = 45 calls**. All numeric scores are exactly repeatable (within-case std = 0) because the current scorer is deterministic. That says nothing about factual accuracy or LLM score consistency. **Human agreement is not calculated**, because there are **zero human-reviewed reference labels**. Reports show `mae_to_human: null` rather than fabricating an accuracy result.

## Human annotation protocol for a real golden set

1. Draft 30–50 varied, consented/de-identified cases spanning excellent, partial, incorrect, off-topic, adversarial, and multilingual answers. Separate training/tuning examples from holdout evaluations.
2. Have at least two reviewers independently grade the question/answer with a **versioned, explicit rubric** for relevance (0–25), technical coverage/correctness (0–35), clarity (0–20), evidence (0–20); ensure reviewers do not see model scores. Use experts for technical correctness and fluent reviewers for Telugu/Hindi as applicable.
3. Adjudicate disagreements and record who reviewed, rubric version, and the resolved dimension grades. Do not use the model's own score as the human reference; that would make evaluation circular.
4. For a reviewed case in `practice_review_queue.json`, set `"review_status": "human_reviewed"` and add:

```json
"reference": {
  "reviewer_id": "pseudonymous-human-reviewer-or-adjudication-id",
  "rubric_version": "rubric-v1",
  "score": 70,
  "dimensions": {
    "relevance": 20,
    "technical_coverage": 25,
    "clarity": 15,
    "evidence": 10
  }
}
```

5. Run the harness again. Then `mae_to_human`, `signed_bias_to_human`, and per-dimension MAE can be meaningfully computed **on the reviewed subset**; the report always records the subset count.
6. Compare two scorers on the **same held-out cases** using paired per-case absolute errors, report differences with uncertainty (e.g., paired bootstrap confidence intervals), and inspect subgroups. A higher mean score is **not** evidence of improved quality. Validate multilingual fairness and avoid protected-attribute proxies.
7. After enough adjudicated cases are available, apply a justified `--max-human-mae` threshold; `--require-all-human-reviewed` guards against interpreting a partial review queue as fully adjudicated. Don't set arbitrary thresholds just to pass CI.

## Explaining this to an AI engineering interviewer

**Question:** "We changed the prompt and scores increased from 3.2 to 4.1. Did quality improve?"

**Answer framework:** "No conclusion from the score increase alone. On a frozen, independently human-reviewed set, I'd compare old and new model scores to human reference dimensions. I would compare *paired* absolute errors, repeat both prompts across multiple independent runs to assess score stability, inspect dimension drift and systematic bias, and quantify uncertainty with confidence intervals. I'd separately measure latency/cost and investigate adversarial/low-quality answers. I'd ship only if the measured improvements hold on a blind holdout, are not offset by worse subgroups or costs, and pass CI regressions."

### Important boundaries

- Current latency is the duration of a local scoring call. It is **not** speech-to-text + LLM + text-to-speech end-to-end timing.
- Current reports are offline smoke checks and snapshot gates; human scoring quality remains **unverified**.
- `OLLAMA_MODEL` affects the optional qualitative coach in the app, and affects the **separate** experimental numerical judge when explicitly requested on the CLI.
- `--scorer ollama` is designed for local experiments only; do not use its numerical results for employment decisions without much more validation.
- Do not publish real candidate transcripts, API keys, or identifiable user recordings in public GitHub repos.
