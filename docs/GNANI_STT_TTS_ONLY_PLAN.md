# Delivery plan with Gnani STT/TTS access only

The available Gnani key has Prisma speech-to-text and Timbre text-to-speech scope. It does not grant Evon semantic evaluation or a documented translation service. This plan uses only those available Gnani model services. The existing text rubric is deterministic application code, clearly labelled as uncalibrated practice feedback; it is not a Gnani semantic model or a verified technical grade.

## Submission scope now

1. **Working voice interview:** Timbre asks the selected technical question; the candidate records an answer; Prisma transcribes it; the candidate can inspect and correct the transcript before submitting. Preserve the original and corrected text as distinct evidence when that review flow is implemented.
2. **Speech settings:** keep Prisma v2.5 as the ordinary default. Offer opt-in Prisma v3.0 `codemix` with `indic-auto` or documented explicit language hints for mixed-language answers. The six human-recorded Hindi/Telugu FLEURS samples favored v2.5 on exact-script words, while a Gnani-generated Telugu-English clip showed v3.0 retaining Latin-script technical terms. Neither sample validates interview semantic accuracy. See [live results](LIVE_GNANI_RESULTS_2026-11-13.md).
3. **Practice feedback:** display the existing evidence-linked text rubric as a practice aid. Show transcript excerpts and missing-concept cues. Never call its score a semantic grade, hiring decision, pronunciation score or expert judgment. Keep the Evon A/B/C experiment unavailable to ordinary users until a real Gnani Evon server is configured and validated.
4. **Demonstration evidence:** show a real Gnani TTS → microphone → Prisma → reviewed transcript → practice-feedback walkthrough. Report provider successes and measured request times separately from any synthetic or public-dataset scores. Use the key only on the server and keep recordings and dataset rows out of the repository.

## Evaluation with present access

- Run paired v2.5/v3.0 ASR checks on the *same* consented Hindi, Telugu, English and mixed-language recordings with human verbatim transcripts. Report word errors with a clearly specified script and number normalizer, plus script-preservation and latency observations. The current six FLEURS clips are a small read-speech check; they cannot establish performance on interviews.
- Have at least two independent reviewers assess a fresh set of technical answers before treating any rubric score as validated. Group a person's answers and translations together in development/test splits. Keep each public dataset's native label scale; Mohler and JorGPT manifests are already prepared for future Evon scoring.
- Present the three Gnani Evon architectures as **implemented experiments with unmeasured semantic performance**. Their comparison becomes executable only with actual Evon access. Do not route to another provider, silently invent a Gnani translation endpoint or describe deterministic keyword checks as model reasoning.

## Decision when Evon access arrives

Serve the documented `gnani/gnani-evon-v3.3-30B-A3B` model on compatible hardware or obtain a documented hosted beta endpoint. First verify identity and successful real responses. Then run the frozen paired A (direct mixed-language), B (Evon translation-assisted), and C (adaptive fallback) harness on JorGPT, Mohler and the new reviewed holdout. Compare native-scale error, per-language disagreement, abstentions and measured end-to-end latency. Promote a path only if the fresh holdout supports it.

References: [Prisma STT API](https://docs.gnani.ai/api/STT/speech-to-text), [Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B), [Evon hosted-access status](https://www.gnani.ai/evon-waitlist).

