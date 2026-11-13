"""Small live human-recorded FLEURS ASR check; credentials stay local."""
import hashlib
import json
import re
import sys
import tarfile
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gnani import GnaniClient, GnaniError


def words(value):
    return re.findall(r"[^\W_]+", value.casefold(), re.UNICODE)


def counts(reference, hypothesis):
    left, right = words(reference), words(hypothesis)
    row = list(range(len(right) + 1))
    for i, token in enumerate(left, 1):
        new = [i]
        for j, other in enumerate(right, 1):
            new.append(min(new[-1] + 1, row[j] + 1,
                           row[j - 1] + (token != other)))
        row = new
    return row[-1], len(left)


def get_samples(config, limit=3):
    base = f"https://huggingface.co/datasets/google/fleurs/resolve/main/data/{config}"
    tsv = requests.get(f"{base}/test.tsv", timeout=60)
    tsv.raise_for_status()
    references = {r[1]: {"raw": r[2], "normalized": r[3]}
                  for line in tsv.text.splitlines() if len(r := line.split("\t")) >= 4}
    response = requests.get(f"{base}/audio/test.tar.gz", stream=True, timeout=120)
    response.raise_for_status()
    found = []
    with response, tarfile.open(fileobj=response.raw, mode="r|gz") as archive:
        for member in archive:
            name = member.name.rsplit("/", 1)[-1]
            if not member.isfile() or name not in references:
                continue
            audio = archive.extractfile(member).read()
            found.append((name, references[name], audio))
            if len(found) == limit:
                break
    if len(found) != limit:
        raise RuntimeError(f"Only {len(found)} FLEURS samples for {config}")
    return found


key = Path(sys.argv[1]).read_text(encoding="utf-8-sig").strip()
if key.startswith("GNANI_API_KEY="):
    key = key.split("=", 1)[1].strip()
if not key or "\n" in key or "\r" in key:
    raise SystemExit("Invalid key file")
client = GnaniClient(api_key=key)
results = []
mode = sys.argv[3] if len(sys.argv) > 3 else "base"
for config, hint in [("hi_in", "hi-IN"), ("te_in", "te-IN")]:
    for filename, reference, audio in get_samples(config):
        item = {"language": config, "file": filename,
                "audio_sha256": hashlib.sha256(audio).hexdigest(),
                "reference_raw": reference["raw"],
                "reference_normalized": reference["normalized"], "stt": []}
        versions = ([("prisma-v3.0", f"{hint},en-IN")]
                    if mode == "hints" else
                    [("prisma-v2.5", hint), ("prisma-v3.0", "indic-auto")])
        for model, language in versions:
            start = time.perf_counter()
            prediction = {"model_requested": model, "language_hint": language}
            try:
                reply = client.transcribe(audio, language, model_version=model)
                errors, total = counts(reference["normalized"], reply["transcript"])
                prediction.update({"transcript": reply["transcript"],
                                   "model_reported": reply["model"],
                                   "detected_language_code": reply["detected_language_code"],
                                   "word_edits": errors, "reference_words": total})
            except GnaniError as exc:
                prediction["error"] = str(exc)
            prediction["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 1)
            item["stt"].append(prediction)
        results.append(item)
        print(f"{config} {filename}: {len(item['stt'])} STT attempts", flush=True)
report = {"source": "google/fleurs test, CC BY 4.0", "type": "live_human_audio",
          "normalization": "Unicode casefold, punctuation removal, whitespace word tokens; no Indic-specific number or spelling normalization",
          "cases": results}
Path(sys.argv[2]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
for config in ("hi_in", "te_in"):
    for model in ("prisma-v2.5", "prisma-v3.0"):
        pairs = [p for c in results if c["language"] == config for p in c["stt"]
                 if p["model_requested"] == model and "word_edits" in p]
        errors = sum(p["word_edits"] for p in pairs)
        total = sum(p["reference_words"] for p in pairs)
        print(json.dumps({"language": config, "model": model, "n": len(pairs),
                          "word_edits": errors, "reference_words": total,
                          "micro_wer": round(errors / total, 4) if total else None}))


