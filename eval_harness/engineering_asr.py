"""Paired, live Gnani Prisma benchmark on licensed human-recorded FLEURS audio.

The detailed JSON stays local and contains transcripts. The public summary has
aggregates only. No credential or audio is written to either output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import struct
import sys
import tarfile
import time
import unicodedata
from pathlib import Path
from urllib.request import urlopen

from gnani import GnaniClient, GnaniError


SOURCE = "https://huggingface.co/datasets/google/fleurs/resolve/main/data"
LANGUAGES = {"hi_in": "hi-IN", "te_in": "te-IN"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text.casefold())
    return " ".join("".join(c if unicodedata.category(c)[0] in "LMN" else " "
                            for c in text).split())


def edit_distance(left: list[str], right: list[str]) -> int:
    row = list(range(len(right) + 1))
    for i, token in enumerate(left, 1):
        next_row = [i]
        for j, other in enumerate(right, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1,
                                row[j - 1] + (token != other)))
        row = next_row
    return row[-1]


def error_counts(reference: str, hypothesis: str) -> dict:
    ref, hyp = normalize(reference), normalize(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    # Code-point CER is reported as a second, still script-sensitive metric.
    ref_chars, hyp_chars = list(ref.replace(" ", "")), list(hyp.replace(" ", ""))
    if not ref_words or not ref_chars:
        raise ValueError("FLEURS reference is empty")
    return {"word_edits": edit_distance(ref_words, hyp_words),
            "reference_words": len(ref_words),
            "char_edits": edit_distance(ref_chars, hyp_chars),
            "reference_chars": len(ref_chars)}


def percentile(values: list[float], fraction: float, digits: int = 1) -> float:
    values = sorted(values)
    if not values:
        raise ValueError("No values")
    at = (len(values) - 1) * fraction
    low, high = int(at), min(int(at) + 1, len(values) - 1)
    return round(values[low] + (values[high] - values[low]) * (at - low), digits)


def sample_audio(config: str, limit: int):
    base = f"{SOURCE}/{config}"
    with urlopen(base + "/test.tsv", timeout=60) as refs_response:
        refs_text = refs_response.read().decode("utf-8")
    refs = {}
    for line in refs_text.splitlines():
        columns = line.split("\t")
        if len(columns) >= 4:
            refs[columns[1]] = columns[3]
    found = 0
    with urlopen(base + "/audio/test.tar.gz", timeout=600) as response, \
            tarfile.open(fileobj=response, mode="r|gz") as archive:
        for member in archive:
            name = member.name.rsplit("/", 1)[-1]
            if not member.isfile() or name not in refs:
                continue
            audio = archive.extractfile(member).read()
            duration = wav_duration(audio)
            yield name, refs[name], audio, duration
            found += 1
            if found >= limit:
                break
    if found != limit:
        raise RuntimeError(f"Expected {limit} {config} samples; found {found}")


def wav_duration(audio: bytes) -> float:
    """Read RIFF duration for PCM or IEEE float WAV without decoding samples."""
    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise ValueError("Expected RIFF WAVE audio")
    offset, byte_rate, data_size = 12, None, None
    while offset + 8 <= len(audio):
        name, size = struct.unpack_from("<4sI", audio, offset)
        offset += 8
        if name == b"fmt " and size >= 16:
            format_code, channels, rate, byte_rate = struct.unpack_from("<HHII", audio, offset)
            if format_code not in (1, 3) or channels < 1 or rate < 1:
                raise ValueError("Unsupported FLEURS WAV format")
        elif name == b"data":
            data_size = size
        offset += size + (size & 1)
    if not byte_rate or data_size is None:
        raise ValueError("FLEURS WAV is missing fmt or data chunk")
    return data_size / byte_rate


def bootstrap_delta(cases: list[dict], repeats: int = 5000) -> list[float]:
    """Paired cluster bootstrap of v3 minus v2 exact-word error rate."""
    rng = random.Random(20261113)
    values = []
    for _ in range(repeats):
        sample = [cases[rng.randrange(len(cases))] for _ in cases]
        words = sum(c["prisma-v2.5"]["reference_words"] for c in sample)
        diff = sum(c["prisma-v3.0"]["word_edits"] -
                   c["prisma-v2.5"]["word_edits"] for c in sample)
        values.append(diff / words)
    return [percentile(values, q, 4) for q in (0.025, 0.975)]


def summarize(cases: list[dict]) -> dict:
    summary = {"sample_method": "first N matching files in FLEURS test audio archive order",
               "metric_note": "Exact-script NFKC, casefold, punctuation-stripped WER and code-point CER; transliteration and semantic equivalence are not normalized.",
               "languages": {}}
    for config in LANGUAGES:
        subset = [c for c in cases if c["language"] == config]
        section = {"clips": len(subset), "models": {}}

        def effective(case: dict, model: str) -> dict:
            first = case.get(model, {})
            return first if "word_edits" in first else first.get("retry", first)

        both = [c for c in subset if all("word_edits" in c.get(m, {})
                                         for m in ("prisma-v2.5", "prisma-v3.0"))]
        after_retry = [c for c in subset if all("word_edits" in effective(c, m)
                                                for m in ("prisma-v2.5", "prisma-v3.0"))]
        for model in ("prisma-v2.5", "prisma-v3.0"):
            rows = [c[model] for c in subset if "word_edits" in c.get(model, {})]
            times = [c[model]["elapsed_ms"] for c in subset
                     if "word_edits" in c.get(model, {})]
            if rows:
                section["models"][model] = {
                    "success": len(rows), "attempts": len(subset),
                    "word_edits": sum(r["word_edits"] for r in rows),
                    "reference_words": sum(r["reference_words"] for r in rows),
                    "micro_wer": round(sum(r["word_edits"] for r in rows) /
                                       sum(r["reference_words"] for r in rows), 4),
                    "micro_cer": round(sum(r["char_edits"] for r in rows) /
                                       sum(r["reference_chars"] for r in rows), 4),
                    "latency_p50_ms": percentile(times, .5),
                    "latency_p95_ms": percentile(times, .95),
                    "median_realtime_factor": round(statistics.median(
                        c[model]["elapsed_ms"] / (c["duration_s"] * 1000)
                        for c in subset if "word_edits" in c.get(model, {})), 3),
                    "failure_types": sorted({c[model]["error"] for c in subset
                                             if "error" in c.get(model, {})}),
                    "retry_attempts": sum("retry" in c.get(model, {}) for c in subset),
                    "retry_success": sum("word_edits" in c.get(model, {}).get("retry", {})
                                         for c in subset),
                }
            else:
                section["models"][model] = {"success": 0, "attempts": len(subset)}
        if both:
            section["paired_clips"] = len(both)
            section["paired_exact_script_wer"] = {
                model: round(sum(c[model]["word_edits"] for c in both) /
                             sum(c[model]["reference_words"] for c in both), 4)
                for model in ("prisma-v2.5", "prisma-v3.0")}
            section["paired_exact_script_cer"] = {
                model: round(sum(c[model]["char_edits"] for c in both) /
                             sum(c[model]["reference_chars"] for c in both), 4)
                for model in ("prisma-v2.5", "prisma-v3.0")}
            section["v3_minus_v2_wer_bootstrap_95pct"] = bootstrap_delta(both)
            section["v3_minus_v2_latency_p50_ms"] = percentile(
                [c["prisma-v3.0"]["elapsed_ms"] - c["prisma-v2.5"]["elapsed_ms"]
                 for c in both], .5)
        if after_retry:
            section["post_retry_paired_clips"] = len(after_retry)
            section["post_retry_paired_exact_script_wer"] = {
                model: round(sum(effective(c, model)["word_edits"] for c in after_retry) /
                             sum(effective(c, model)["reference_words"] for c in after_retry), 4)
                for model in ("prisma-v2.5", "prisma-v3.0")}
            section["post_retry_paired_exact_script_cer"] = {
                model: round(sum(effective(c, model)["char_edits"] for c in after_retry) /
                             sum(effective(c, model)["reference_chars"] for c in after_retry), 4)
                for model in ("prisma-v2.5", "prisma-v3.0")}
        summary["languages"][config] = section
    return summary


def run(key_file: Path, detail_file: Path, summary_file: Path, limit: int,
        retry_failed: bool = False) -> dict:
    key = key_file.read_text(encoding="utf-8-sig").strip()
    if key.startswith("GNANI_API_KEY="):
        key = key.split("=", 1)[1].strip()
    if not key or "\n" in key or "\r" in key:
        raise ValueError("Invalid local key file")
    client = GnaniClient(api_key=key)
    cases = (json.loads(detail_file.read_text(encoding="utf-8"))["cases"]
             if detail_file.exists() else [])
    existing = {(c["language"], c["file"]): c for c in cases}
    try:
        for config, hint in LANGUAGES.items():
            for index, (filename, reference, audio, duration) in enumerate(sample_audio(config, limit)):
                old = existing.get((config, filename))
                if old and not retry_failed:
                    print(f"{config} {index + 1}/{limit} resumed", flush=True)
                    continue
                if retry_failed and (not old or not any(
                        "error" in old.get(m, {}) and "retry" not in old[m]
                        for m in ("prisma-v2.5", "prisma-v3.0"))):
                    continue
                item = old if retry_failed else {"language": config, "file": filename,
                                                   "audio_sha256": hashlib.sha256(audio).hexdigest(),
                                                   "duration_s": round(duration, 3), "reference": reference}
                # Alternate call order to reduce a systematic order advantage.
                models = ("prisma-v2.5", "prisma-v3.0") if index % 2 == 0 else (
                    "prisma-v3.0", "prisma-v2.5")
                if retry_failed:
                    models = tuple(m for m in models if "error" in item.get(m, {})
                                   and "retry" not in item[m])
                for model in models:
                    language = hint if model == "prisma-v2.5" else "indic-auto"
                    start = time.perf_counter()
                    try:
                        reply = client.transcribe(audio, language, model_version=model)
                        outcome = {"transcript": reply["transcript"],
                                   "model_reported": reply["model"],
                                   "detected_language_code": reply["detected_language_code"],
                                   **error_counts(reference, reply["transcript"])}
                    except GnaniError as exc:
                        outcome = {"error": str(exc)}
                    outcome["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 1)
                    if retry_failed:
                        item[model]["retry"] = outcome
                    else:
                        item[model] = outcome
                if not retry_failed:
                    cases.append(item)
                detail_file.write_text(json.dumps({"cases": cases}, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
                print(f"{config} {index + 1}/{limit}" + (" retried" if retry_failed else ""), flush=True)
    finally:
        client.client.close()
    summary = summarize(cases)
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--detail", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--clips-per-language", type=int, default=12)
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Retry each first-attempt failure once without overwriting it")
    args = parser.parse_args()
    if not args.run_live:
        parser.error("This sends audio to Gnani. Supply --run-live explicitly.")
    if not 1 <= args.clips_per_language <= 100:
        parser.error("clips-per-language must be 1..100")
    result = run(args.key_file, args.detail, args.summary, args.clips_per_language,
                 retry_failed=args.retry_failed)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

