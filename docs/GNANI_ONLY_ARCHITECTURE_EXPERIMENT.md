# Gnani-only semantic experiment (13 November 2026)

## What is implemented

- **A, direct:** one immutable Prisma transcript is scored by locally served Gnani Evon v3.3 against a question and reference answer.
- **B, translation-assisted:** the same Evon model translates that transcript into English, then scores the translation with the same scoring prompt. Translation is an *experimental Evon task*, not a claimed Gnani translation API. The translated evidence is marked as translation-only; the original transcript is preserved.
- **C, adaptive:** reuse A's result. Invoke B only if A says `uncertain` or supplies no verbatim answer evidence. If the paths disagree by more than two points or B is uncertain, abstain for human review. The benchmark runs A and B on every case to allow paired comparison; its C timing is explicitly a counterfactual sum of whichever calls C would need.

The main app's existing heuristic feedback remains a practice baseline. Its optional Ollama refinement is no longer called. Semantic experiments run through `POST /api/semantic/evaluate` with a local Evon server; the API returns both paths and the hybrid decision, not a validated hiring grade. Prisma v2.5 remains the app default; `/api/transcribe` accepts `stt_model=prisma-v3.0` and `language=indic-auto` for v3 code-mixed transcription. The original STT method is backward compatible.

## Provider access and reproducibility

No live Gnani call was made for this change. No API key or running Evon service was found in the execution environment. `GNANI_EVON_BASE_URL` must point to a **local** HTTP server actually serving `gnani/gnani-evon-v3.3-30B-A3B` under that exact model name. The published [Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B) documents vLLM's `/v1/chat/completions` transport and the needed GPU class. Using an OpenAI-compatible *wire format* does not send data to OpenAI. A URL or model ID outside the allowed local Gnani configuration is rejected. A running server, model identity, quality and latency must be verified by the operator before reporting provider results.

Example local startup, only on a compatible Linux GPU host with model access:

```sh
vllm serve gnani/gnani-evon-v3.3-30B-A3B --served-model-name gnani/gnani-evon-v3.3-30B-A3B --port 8000
```

Set `GNANI_EVON_BASE_URL=http://127.0.0.1:8000` in the server environment, then use `/api/semantic/evaluate` or the harness. The Evon model card indicates that access conditions may require signing in and that hardware requirements are substantial. Do not present this as a hosted Gnani API.

## Dataset decisions

| Source | Role | Native metric and caveat |
| --- | --- | --- |
| [JorGPT](https://zenodo.org/records/18981627) | University answer grading, especially programming-related questions after topic filtering | Teacher numerical grades; Spanish/English parallel content must stay in one variant family. Its 79 student identities support person-grouped splits. Confirm the record's exact license and column mapping before importing. |
| [Mohler ASAG](https://huggingface.co/datasets/nkazi/MohlerASAG) | English computer-science short-answer grading | Two graders and average scores on a 0–5 scale. The public mirror has no clear person identifier in the displayed schema, so a person-disjoint test cannot be claimed without provenance. Confirm reuse terms. |
| [SemEval 2013 Task 7](https://huggingface.co/datasets/Atomi/sem_eval_2013_task_7) | Correctness, contradiction, incompleteness checks | Preserve 2-way, 3-way or 5-way labels as their distinct tasks. Do not convert categories into 0–10 scores. Follow official split, corpus and question IDs. Check mirror permissions. |
| [Indic-MMLU-Pro](https://huggingface.co/datasets/ai4bharat/indic-mmlu-pro) | Multilingual question comprehension, separate multiple-choice stress test | Choice accuracy, not candidate answer grading. Evon's model card already reports Indic-MMLU-Pro, so contamination is plausible; do not use it as independent validation. |
| [ScAA](https://aclanthology.org/2020.icon-main.58/) | Hindi/Marathi short-answer correctness, if files and rights are confirmed | Binary correct/incorrect on children's science answers. This is not a technical interview score. Paper availability does not establish dataset reuse permission. |
| [IndicVoices](https://huggingface.co/datasets/ai4bharat/IndicVoices) | Prisma ASR WER by language and acoustic condition | Audio and transcripts, not interview grades. Dataset card states CC BY 4.0 but access requires accepting its conditions. |
| Fresh consented mixed-language set | Primary decision set | New technical questions and answers, two independent blinded reviewers, original audio and transcript, stratified languages and noise. No such labels have been collected here. |

No external dataset rows were copied into this change, because access, licensing, mapping and provenance were not fully verified. The local manifest is supplied by the study operator. This also avoids treating public benchmark exposure as a new-person interview test.

## Benchmark procedure

1. Obtain dataset files with permission. Preserve source, license, original IDs, question, reference, original score/label and language. Add `person_id` and `variant_group_id` based on reliable metadata; use the same `variant_group_id` for translations and paraphrases. Do not invent missing person identities.
2. Freeze `development` and `test` before tuning prompts or thresholds. The manifest validator rejects a person or variant family in both. For `fresh_mixed_holdout`, record consent, two independent reviewer IDs and an adjudicated label. Keep raw reviewer judgments separately.
3. Run `python -m eval_harness.gnani_paths --manifest local_manifest.json --output result.json` to validate structure without a provider call. Run with `--run-live` only after confirming local Evon access. Results and translations can contain candidate text; keep them private.
4. Measure Prisma v2.5 versus v3.0 separately using identical consented audio, manual reference transcripts and WER. Use a single cached transcript for each paired A/B/C comparison. Record audio duration, language, model, transcription time, translation time, scoring time, end-to-end time, errors and abstentions.
5. Compare native metrics *per dataset*: numerical MAE on each source's own scale, categorical accuracy for native labels, paired score deltas, per-language differences, human review/abstention rates, and latency distributions. The harness scales Evon's 0–10 output into each numeric dataset's native range for descriptive MAE; this does not calibrate the model to that source.
6. Repeat with the fresh, never-used holdout. Inspect technical negation, partially correct reasoning, code-mixed terms and translation changes with reviewers blind to model scores. Do not tune on holdout errors.

Manifest case fields: `id`, `dataset`, `split`, `person_id`, `variant_group_id`, `question`, `reference`, `transcript`, `label_kind` (`none`, `numeric`, `categorical`), plus `label` and `label_max` for numeric labels or `label` and `label_namespace` for categorical labels. Native categorical labels incompatible with InterviewMirror's four-way verdict are explicitly excluded from generic categorical accuracy until a separate task adapter is built. A fresh holdout additionally needs `reviewer_ids` (at least two distinct values) and `consent_recorded=true`.

## Current results and remaining limits

The new targeted tests exercise mock transport and scripted responses only. They measure pipeline behavior, schema validation and failure handling; they are **not** Gnani quality results. No real A/B/C correctness, fairness, WER, cost or latency number exists yet. Evon's published multilingual and translation-related benchmarks are provider claims on different tasks, not evidence that translation helps InterviewMirror. The direct path is the operational default hypothesis because it avoids a transformation and one Evon call, while the A/B test determines whether that translates to better measured accuracy or latency on this task.

Sources: [Prisma REST specification](https://docs.gnani.ai/api/STT/speech-to-text), [Prisma v3 model overview](https://docs.gnani.ai/api/STT/models/prisma-v3), [Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B), [official internship terms](https://www.gnani.ai/great-indian-ai-internship-registration-form).

