# Dataset and evaluation status

**Current status, 15 November 2026.** This document describes files actually present in this project archive. It supersedes prior drafts that referred to unbundled `work/` manifests or results that cannot be reproduced from this archive.

## Current inventory

| Asset | Present here | What it supports | What it does not prove |
|---|---|---|---|
| `eval_harness/datasets/practice_review_queue.json` | Yes | Synthetic functional and scorer-regression cases | Human correctness, semantic accuracy, hiring validity, or fairness |
| `eval_harness/datasets/calibration_benchmark_v3.json` | Yes | A local synthetic calibration/probe set | Independent human-gold calibration |
| `eval_harness/datasets/gold_holdout_template.json` | Yes; 0 cases | Consent, annotation, leakage, review and holdout-sealing workflow | Any human-reviewed gold examples |
| JorGPT and Mohler importers | Code only | Rights-aware local import and native-label validation | Imported records or model scores; no data manifests are bundled |
| SemEval, ScAA, Indic-MMLU-Pro, IndicVoices | Research notes only | Suitability and licensing considerations | Ingestion, scoring, or target-domain validation |
| FLEURS / live ASR reports | Historical notes only | Prior small read-speech observations recorded in docs | Reproducible results from audio and per-utterance manifests in this archive |

Never label the synthetic practice cases as gold. Do not merge JorGPT's 0–10 grade, Mohler's 0–5 score, or incompatible categorical labels into a shared score. These public educational short-answer datasets can be separate external reference tasks if their source data and licenses are acquired and verified; they are not a substitute for a fresh mixed-language interview holdout.

## Gold-data workflow

`eval_harness/gold_evaluation.py` defines the case and rubric schema. `eval_harness/gold_workflow.py` provides a private local annotation CLI. The CLI requires explicit consent, a PII-redaction declaration, pseudonymous participant IDs, two distinct reviewers, exact evidence quotes, score bounds, and adjudication when reviewer verdicts differ or scores differ by more than 15 points. It prevents person, question-family, and exact-answer leakage across splits. A sealed ready set must have a nonempty locked holdout and a matching SHA-256 digest. Sealing detects accidental edits; protect the sealed file with access controls and immutable version control as well.

The supplied template intentionally has zero cases. To prepare a dataset, add only real consented and PII-redacted cases with pseudonymous IDs to a private, unsplit intake JSON. Assign `split` before annotation, keeping every participant and translated/paraphrased question family together:

```powershell
python -m eval_harness.gold_workflow partition --input PATH_TO_PRIVATE_UNSPLIT_INTAKE.json --output PATH_TO_PRIVATE_SPLIT_DATASET.json --test-ratio 0.2 --calibration-ratio 0.1
```

The requested proportions are targets: connected participants/families stay together, so the resulting counts may differ. The command reports actual counts. Continue with the resulting dataset:

```powershell
python -m eval_harness.gold_workflow status --dataset eval_harness/datasets/gold_holdout_template.json
python -m eval_harness.gold_workflow validate --dataset PATH_TO_PRIVATE_DATASET.json
python -m eval_harness.gold_workflow export-review-forms --dataset PATH_TO_PRIVATE_DATASET.json --output-dir PATH_TO_PRIVATE_REVIEW_FORMS --reviewers reviewer_a reviewer_b
```

Reviewers work on separate files. Each form's `rating` object must contain `timestamp_utc`, all rubric `dimensions`, `total_score`, `verdict`, `evidence_quotes`, and `rationale`. Return one form at a time with:

```powershell
python -m eval_harness.gold_workflow import-review --dataset PATH_TO_PRIVATE_DATASET.json --form PATH_TO_RETURNED_REVIEW.json
```

For disagreements, export an independent adjudication form, fill `resolved_adjudication` with `timestamp_utc`, `resolved_dimensions`, `resolved_score`, `resolved_verdict`, and `resolution_rationale`, then import it:

```powershell
python -m eval_harness.gold_workflow export-adjudication-form --dataset PATH_TO_PRIVATE_DATASET.json --case-id CASE_ID --adjudicator-id independent_adjudicator --output PATH_TO_PRIVATE_ADJUDICATION.json
python -m eval_harness.gold_workflow import-adjudication --dataset PATH_TO_PRIVATE_DATASET.json --form PATH_TO_COMPLETED_ADJUDICATION.json
```

After all cases have two reviews and required adjudications, validate and seal:

```powershell
python -m eval_harness.gold_workflow validate --dataset PATH_TO_PRIVATE_DATASET.json
python -m eval_harness.gold_workflow seal --dataset PATH_TO_PRIVATE_DATASET.json
```

Private candidate answers and review forms must stay outside public Git, reports, and support logs. Do not commit them. The repository does not contain a case intake source or actual reviewers; a real gold set still requires participants, consent, and qualified human work.

## Model status and valid claims

- The active real-time path uses Gnani Prisma STT and Timbre TTS when the owner configures a working key. A key's presence does not establish provider access.
- The interview rubric and adaptive question policy remain deterministic practice logic. They are not human-calibrated semantic evaluations.
- The optional A/B/C semantic experiment is restricted to the documented Gnani Evon model served locally. The available STT/TTS key does not grant Evon or translation access. Do not substitute another provider, invent a translation endpoint, or report an Evon score without an authorized running Gnani Evon server.
- Evaluate every dataset on its own label and scale. For numerical labels report MAE and uncertainty on that native scale; for categorical labels use task-compatible confusion matrices and macro-F1. Report language/code-mix strata only where the sample size supports interpretation. Preserve the final holdout from tuning.

## Reproducible checks

```powershell
python -m pytest tests/test_golden_imports.py tests/test_gold_workflow.py -q
python -m eval_harness.run --dataset eval_harness/datasets/practice_review_queue.json --scorer robust --repeats 5
```

The first command validates code paths; it is not a human-labeled accuracy evaluation. The second reports synthetic scorer behavior only. No golden-set or semantic model-quality metric is available until real labeled cases and the authorized evaluator are present.

After sealing a human-reviewed holdout, export a private manifest for the Gnani-only A/B/C harness:

```powershell
python -m eval_harness.gold_workflow export-gnani-holdout-manifest --dataset PATH_TO_SEALED_DATASET.json --output PATH_TO_PRIVATE_MANIFEST.json
python -m eval_harness.gnani_paths --manifest PATH_TO_PRIVATE_MANIFEST.json --output PATH_TO_PRIVATE_RESULTS.json
```

The second command only validates the manifest offline unless `--run-live` is supplied. A live A/B/C run requires a separately authorized Gnani Evon service endpoint; the user's current STT/TTS key is not enough. Keep the manifest and results private because they contain interview responses. The exporter is tested with temporary mock records only; those are not bundled as project gold data and do not count as evaluation results.
