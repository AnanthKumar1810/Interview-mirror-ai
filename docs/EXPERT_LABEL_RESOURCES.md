# External scoring references: suitability and annotation protocol

**Status: research and integration guidance, not a claim that our existing scores have been expert-validated.**

## Relevant sources

1. **SemEval-2013 Task 7 / BEETLE / SciEntsBank** — https://huggingface.co/datasets/Atomi/sem_eval_2013_task_7
   - Human-annotated short-answer correctness examples with reference answers and 2/3-way labels; BEETLE also includes partial/contradictory/irrelevant distinctions.
   - Useful for testing whether a semantic correctness detector recognizes contradictions and meaning preservation.
   - **Not** technical interview performance: much content is science-education answers, not AI-engineering interviews, and labels are categorical, not our 0–100 rubric. Do not transfer numeric scores directly.
   - Confirm dataset redistribution permissions, provenance, deduplicate reference-answer joins, and preserve official train/test splits before importing.
2. **ML Systems Interview Bench** — https://huggingface.co/datasets/Max00035/ml-systems-interview-bench
   - Interview-style ML engineering questions with expected concepts, reference answers and rubric anchors.
   - Useful for question bank breadth and constructing independently reviewed examples.
   - **Not expert-labelled candidate responses** and not a validated hiring score. Check dataset license/terms before redistribution.
3. **ASAP short-answer scoring (ASAP-SAS)** — see https://doi.org/10.1007/S40593-014-0026-8
   - Human-scored educational short answers. Useful for research into inter-rater agreement, rubric calibration and quadratic weighted kappa.
   - Questions and scores are domain-specific; direct calibration of InterviewMirror using these would be invalid.

## Human annotation procedure for our AI/ML/agentic questions

- Keep an immutable `question_id`, text, language, track, reference answer, and expected concept rubric.
- Collect consented responses; redact names, phone numbers, emails and sensitive details.
- Require **two independent qualified reviewers** to score each dimension (relevance 0–25, technical concept coverage 0–35, textual clarity 0–20, verifiable evidence 0–20). Label correctness separately as correct / partly correct / incorrect / cannot assess.
- Record reviewer identifier (pseudonymous), timestamp, rubric version, disagreement and concrete evidence spans. Reviewers must not see the model's score while labelling.
- Resolve large disagreements with adjudication, keeping both original reviews.
- Split at the **question or candidate level**, not randomly duplicated paraphrases, to prevent train/test leakage. Freeze the held-out set before score-rule updates.
- Use `eval_harness/datasets/practice_review_queue.json` as the schema for adjudicated results: `review_status='human_reviewed'`, a `reference` with `score`, `dimensions`, `reviewer_id`, `rubric_version`. One adjudicated record per case; do not manufacture labels from the model's own output.
- Run `python -m eval_harness.run --dataset PATH --scorer robust --repeats 5` and compare: dimension MAE, total-score MAE, high-score rate on incorrect answers, Spearman ranking on adjudicated cases, score drift and language-specific error. Our current harness computes MAE and drift only when labels are present; Spearman and incorrect-answer audits require explicitly tracked correctness labels and a separate script.

**Present state:** The bundled nine-case practice dataset contains synthetic answers and **zero human-reviewed references**. The external sources above are not already imported, and no expert-agreement score is claimed.
