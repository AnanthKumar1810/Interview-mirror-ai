# Evaluation workbench implementation report — 26 November 2026

## Scope and existing implementation

Starting revision: `65bcfa0cc0899804ab349d313317638cc5c494e9` on main.
The repository already contained deterministic scoring, repeated-run evaluation,
per-dimension drift gates, verbatim heuristic evidence, synthetic adversarial
probes, an optional unvalidated Ollama judge, and a consented multi-reviewer gold
annotation workflow. These were inspected and reused, not claimed as new work.

## Changes made in this pass

- Added paired-score MAE, signed bias, Pearson correlation and tied-rank Spearman
  correlation. Empty, constant and insufficient samples return null correlations;
  nonfinite values and unequal arrays are rejected. Correlation is not accuracy.
- Added categorical Cohen kappa and a gold-dataset agreement command. Comparisons
  retain actual reviewer-pair identities instead of pooling unrelated reviewers.
- The harness now checks every provided evidence quote against the candidate's
  exact answer, checks its rubric dimension and requires an observation. It
  stores evidence for each repeat. Membership is not semantic support validation.
- Added --require-evidence as an opt-in gate and enabled it in both CI scorer
  runs. Nonfinite/negative gate thresholds are rejected before scoring begins.
- The evidence gate found one generic answer scored 2 for structure without an
  evidence item. The scorer now quotes the actual answer with its observed word
  and clause counts and explicitly identifies this as a structural heuristic.
  The score and all checked-in baseline scores remain unchanged.
- Added a standalone HTML workbench showing scores, dimensions, repeat variation,
  first-repeat evidence, human references, agreement and gate results. It escapes
  source/model text and retains every repeat in the source JSON.
- CI renders and uploads the workbench and synthetic evaluation reports.

## Reproduced experiments

Dataset: synthetic-practice-review-queue-v2; 13 existing constructed cases.
SHA-256: `209d58b0380135d31ea8124a902ae901bacfb702e66411d1692a099805739bbf`.

| Check | Measured result |
|---|---|
| Heuristic scorer | 13 cases x 5 repeats = 65 calls |
| Risk-aware scorer | 13 cases x 5 repeats = 65 calls |
| Within-case score SD | 0 for both deterministic scorers |
| Total and per-dimension drift | 0 against their respective checked-in baselines |
| Evidence coverage before structural explanation fix | 60/65 calls for each scorer |
| Evidence coverage after fix | 65/65 calls for each scorer |
| Existing synthetic adversarial gate | PASS; 0/2 robust high scores versus 1/2 heuristic high scores |
| Actual human-reviewed cases | 0 |
| Actual human MAE/Pearson/Spearman/kappa | Unmeasured, not zero |
| Human-MAE gate without references | Correctly exits 1 |
| NaN threshold | Correctly rejected with exit 2 before scoring |

The adversarial behavior predates this pass; this work revalidated it. The
synthetic cases were already inspected and are not a blinded holdout. Zero
variation from a deterministic heuristic does not establish LLM score stability.

## Tests and environment

The final full suite passed 295 tests with 1 optional native LiveKit test
skipped in 41.61 seconds on Python 3.12.14. Eighteen new tests cover this pass.
The first full run encountered missing SOCKS proxy support in this
execution environment; installing its optional socksio/PySocks dependencies
resolved those environment errors. One native LiveKit adapter test is skipped
because that optional runtime is unavailable. No live voice call or live LLM
judge was run in this pass. The correlation tests compare against SciPy and
cover ties, constants, malformed pairs and high correlation with large bias.
Additional tests cover fabricated evidence, HTML escaping, reviewer grouping,
missing-evidence gating, empty gold data and pre-scoring threshold rejection.

## Reproduce

```bash
python -m pytest -q
python -m eval_harness.run --scorer robust --repeats 5 --compare reports/risk_aware_baseline.json --max-absolute-score-drift 0 --max-within-case-std 0 --require-evidence --output reports/workbench.json
python -m eval_harness.workbench --report reports/workbench.json --output reports/workbench.html
python -m eval_harness.agreement --dataset eval_harness/datasets/gold_holdout_template.json --output reports/human_agreement.json
```

For actual quality measurement, obtain independent reviewed answers through the
existing gold workflow and run the desired scorer on them. Do not substitute
model-generated labels or these synthetic tests for human references. Workbench
HTML may contain answer excerpts; keep reports generated from private data out
of public GitHub artifacts.
