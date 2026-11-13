# Live Gnani speech results — 13 November 2026

This combines a provider integration smoke test with a small, human-recorded ASR check. It is not interview scoring validation. The user supplied an STT/TTS-scoped Gnani key locally. The key is not stored in this repository or in the results.

## Method

Gnani Timbre v2.5 generated four short WAV clips from fixed text: English, Telugu, Hindi, and Telugu–English mixed. Each *same WAV* was sent once to Prisma v2.5 (`transcribe`) and once to Prisma v3.0 (`codemix`, `indic-auto`). A separate repeat of the mixed text compared `indic-auto` with v3.0's documented `te-IN,en-IN` hints. All requests used the [official REST STT endpoint](https://docs.gnani.ai/api/STT/speech-to-text) through the existing project client. Elapsed times are local wall-clock times and include network transfer. These are single observations, not stable latency estimates.

| Timbre input | TTS ms | v2.5 STT ms | v3.0 STT ms | v3 detected |
| --- | ---: | ---: | ---: | --- |
| English | 4,689 | 4,054 | 2,460 | en-IN |
| Telugu | 2,971 | 2,158 | 1,478 | te-IN |
| Hindi | 2,510 | 1,328 | 1,125 | hi-IN |
| Telugu–English | 2,971 | 1,228 | 1,126 | te-IN |

**Result:** 4/4 TTS and 8/8 STT calls returned successfully. On this one-run matrix, v3.0 returned faster than v2.5 in each paired case. That does not establish a population-level speed advantage.

For the mixed clip, Prisma v2.5 returned `ఓవర్ ఫిట్టింగ్ అంటే ట్రైనింగ్ డేటా మీద ఆక్యురసీ ఎక్కువ కానీ న్యూ డేటా మీద పర్ఫార్మెన్స్ తక్కువ`. Prisma v3.0 returned `overfitting అంటే training data మీద accuracy ఎక్కువ కానీ new data మీద performance తక్కువ.` This verifies that v3.0's code-mix format preserved the Latin-script technical terms in this sample. It does **not** establish which transcript more faithfully represents a human speaker.

In a separate generation of the same mixed phrase, v3.0 with `indic-auto` returned a transcript in 1,202 ms; with explicit `te-IN,en-IN` hints it returned a near-identical transcript in 923 ms. This one pair cannot establish that hints improve accuracy or latency generally. The code now accepts both documented hint forms.

## Human-recorded FLEURS check

Six recordings were sampled deterministically from the first three audio files in each of the Hindi and Telugu [FLEURS test archives](https://huggingface.co/datasets/google/fleurs) (CC BY 4.0). The reference text is the dataset's human transcript, not a TTS input. Each identical audio clip was sent to Prisma v2.5 with its language hint, Prisma v3.0 with `indic-auto`, and v3.0 with `hi-IN,en-IN` or `te-IN,en-IN`. All 18 live STT calls succeeded. This is a tiny convenience sample of read speech, not candidate speech or a representative estimate.

The reproducible probe is `eval_harness/live_fleurs.py`. Run `python eval_harness/live_fleurs.py PATH_TO_LOCAL_KEY results.json` and repeat with a separate result path and `hints` as the final argument. The key is read from the local file and is not written to either result. The script streams only the required samples from the source archives.

| Language | Clips | Reference words | v2.5 word edits | v3.0 word edits, auto | v3.0 word edits, explicit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hindi | 3 | 171 | 1 | 35 | 35 |
| Telugu | 3 | 128 | 1 | 24 | 24 |

The word-edit calculation lowercases text, removes punctuation, and compares whitespace-delimited words. It does **not** normalize transliteration, Indic spelling variants or number forms. These are script-sensitive exact-word counts, **not comparable semantic accuracy estimates**. For example, the v3.0 output uses `Greenland`, `France`, and `objects` where the FLEURS reference uses Indic-script forms. There are also content differences, including a duplicated phrase in one Telugu v3.0 response. All six v3.0 explicit-hint transcripts were identical to their corresponding `indic-auto` transcripts. Across six clips, the median local wall-clock request time was 2,074 ms for v2.5, 1,927 ms for v3.0 auto, and 2,142 ms for v3.0 explicit hints; one call per configuration and clip is insufficient to infer provider latency rankings.

**Implementation decision:** retain v2.5 as the default for ordinary monolingual speech. Expose v3.0 as an explicit code-mix option and preserve the original transcript so downstream reviewers can inspect language/script choices. Do not route by these six exact-word counts alone; a human-reviewed mixed-language interview sample is required to choose routing and evaluate meaning retention.

## Full app-route smoke

A separate local FastAPI app-route check used the supplied key without storing it in the repository. It loaded the interview page, created a session, generated one English answer with `/api/speak`, converted Timbre's 24 kHz WAV into the browser upload path's 16 kHz mono PCM WAV, called `/api/transcribe` with `prisma-v3.0` and `indic-auto`, and submitted the returned transcript to `/api/answer`. Every route succeeded. The returned transcript exactly matched the synthetic answer text in this one run. The Timbre and Prisma calls took 3,787 ms and 3,263 ms respectively, measured locally including network transfer. The feedback's numeric practice score was not evaluated against a human grade. This checks backend integration, not a real microphone or real interview response.

## What is still missing

- The four Timbre clips were generated, not spoken by candidates. Their input text is not an independently checked verbatim audio reference. The six FLEURS recordings do have human transcripts, but represent read Hindi/Telugu speech. Their simple word-edit metric is script-sensitive and should not be used as a semantic or mixed-language interview score.
- The available key is scoped to STT/TTS. [Gnani describes Evon API access as a selected closed beta](https://www.gnani.ai/evon-waitlist), while the [Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B) lists A100/H100/H200-class self-hosting hardware. No live Evon evaluation or translation was run. A/B/C scores, score agreement and timing remain unmeasured.
- No independently human-reviewed Telugu–English technical-answer holdout or real candidate recordings were available. Scores on public datasets cannot replace that test.

## Golden data prepared without model inference

- [Mohler ASAG](https://huggingface.co/datasets/nkazi/MohlerASAG) declares CC BY 4.0. Its 2,273 open-ended rows were imported with both original graders and the original 0–5 average. All are test-only because the public mirror does not provide reliable student identities.
- [JorGPT v3](https://zenodo.org/records/18981627) declares CC BY 4.0. The two 3,041-row language files were checked for paired entry IDs, student IDs, question IDs and identical teacher grades. A deterministic student-disjoint split used 16 of 79 students for test. Ten blank-answer pairs and 25 development entries duplicating test text were excluded, leaving 6,012 English/Spanish cases. The English-only manifest contains 3,006 cases. Spanish is outside Evon's listed supported languages and is kept for pairing/leakage control, not a claimed supported-language result.

These manifests are local private data files. No Evon predictions, human-agreement metrics or dataset-derived scoring claims were generated. The importer source and tests are in this PR so the preparation is reproducible.

