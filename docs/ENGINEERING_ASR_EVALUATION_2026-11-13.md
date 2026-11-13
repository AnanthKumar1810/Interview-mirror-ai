# Engineering ASR evaluation — 13 November 2026

## Scope and method

This is a live, paired Gnani speech-recognition check using the user's STT/TTS-only key. It is separate from the Evon A/B/C semantic experiment. The public [FLEURS Hindi and Telugu test recordings](https://huggingface.co/datasets/google/fleurs) have human reference transcripts and a CC BY 4.0 dataset license. We selected the first 12 matching audio files in each language's test archive: **24 read-speech clips**. The sample is deterministic but not random or representative of interviews. Public speech may also be familiar to providers.

Each identical clip was sent once to Prisma v2.5 with `hi-IN` or `te-IN`, and once to Prisma v3.0 with `indic-auto` and `codemix` output. Model call order alternated across clips. The run recorded audio duration, file hash, returned model, transcript, first-attempt wall-clock latency, and any provider error. Six failed first attempts were retried once; original errors and timings were retained. The benchmark sent no interview-specific keyterms, while the main app can send question-bank hints, so these figures describe the baseline client configuration rather than every app setting. The private transcript-level JSON and the API key were not committed.

The public aggregate script is `eval_harness/engineering_asr.py`. Exact-script word error rate (WER) and code-point character error rate (CER) use Unicode NFKC, case folding, punctuation removal, and whitespace word boundaries. They **do not equate transliterated words or judge meaning**. FLEURS references often spell borrowed words in Indic script; v3.0's code-mix output often uses Latin script. A paired bootstrap interval is descriptive for this convenience sample, not a population claim.

## Measured results

| Language | First-attempt paired clips | v2.5 WER / CER | v3.0 WER / CER | After one retry, paired WER v2.5 / v3.0 |
| --- | ---: | ---: | ---: | ---: |
| Hindi | 10/12 | 9.35% / 2.81% | 16.19% / 17.99% | 9.09% / 15.99% on 12 clips |
| Telugu | 10/12 | 15.65% / 1.98% | 26.53% / 16.02% | 18.69% / 27.78% on 12 clips |

All **48 first attempts** were made; **42 returned transcripts**. Four Hindi calls failed during a network interruption (two connection failures for v2.5, one connection failure and one timeout for v3.0). Two Telugu v2.5 calls returned HTTP 504. **All six succeeded on one retry.** The main app does not automatically retry provider calls; this recovery check is diagnostic and would add delay and possibly provider usage if adopted.

Successful first-attempt local wall-clock latency, including network transfer:

| Language | v2.5 p50 / p95 | v3.0 p50 / p95 | Median paired v3.0 − v2.5 |
| --- | ---: | ---: | ---: |
| Hindi | 6,828 / 23,184 ms | 5,258 / 14,059 ms | −581 ms |
| Telugu | 1,216 / 1,583 ms | 1,213 / 1,349 ms | −38 ms |

Latency is highly variable in the Hindi run. There was one request per model and clip; no stable provider speed or cost ranking follows. The only measured usage proxy is 48 initial STT requests plus six retries. No price was assumed.

The first-attempt paired exact-script WER difference (v3.0 minus v2.5) had a clip-bootstrap 95% interval of **+0.84 to +12.82 percentage points** for Hindi and **+4.44 to +17.83 points** for Telugu. This interval reflects the selected clips and the specified script-sensitive metric. For example, a Hindi reference writes Greenland in Devanagari while v3.0 returned `Greenland`; Telugu references likewise use Indic spellings where v3.0 returned `France` and `objects`. Some responses also contain apparent word substitutions or repeated phrases. These need independent review before a semantic accuracy claim.

## Engineering decisions and next checks

1. Keep **v2.5 as the ordinary default**. It matched the supplied Hindi and Telugu reference scripts more closely in this sample. Retain **v3.0 as an explicit code-mix option** because it preserves Latin technical terms in the earlier Telugu-English smoke test. Neither result proves a better interview transcript.
2. Keep human transcript review before feedback. The UI should show the selected STT model and detected language with the editable transcript. When a provider request fails, let the user retry explicitly; an automatic retry may add latency or duplicate a charge if delivery status is uncertain.
3. Build a consented, independently transcribed **real technical-answer holdout** in English, Telugu, Hindi, and mixed Telugu-English/Hindi-English. Review content and script choices separately, record corrections, and compare both models on identical audio. Group answers by speaker. Assess code-mixed technical terms, negation, and noisy conditions. Do not use public FLEURS performance as a new-interview generalization claim.
4. Maintain the current deterministic practice rubric as uncalibrated feedback. The 0–100 number is not an expert technical grade. No live Evon translation or semantic path was run with this key; A/B/C quality, fairness, and end-to-end semantic latency remain unmeasured.

Reproduction: `python -m eval_harness.engineering_asr --key-file PATH_TO_LOCAL_KEY --detail PRIVATE_DETAIL.json --summary PRIVATE_SUMMARY.json --clips-per-language 12 --run-live`. To retry only failures once, use the same paths with `--retry-failed`. These commands send audio to Gnani and use provider credits. The local key path and private files should stay outside the repository.

