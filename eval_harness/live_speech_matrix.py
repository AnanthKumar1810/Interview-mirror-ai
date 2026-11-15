"""Private, small live Gnani speech smoke matrix; never prints credentials."""
import json
import re
import sys
import time
from pathlib import Path

from gnani import GnaniClient, GnaniError


def tokens(text):
    return re.findall(r"[^\W_]+", text.casefold(), re.UNICODE)


def wer(reference, prediction):
    a, b = tokens(reference), tokens(prediction)
    row = list(range(len(b) + 1))
    for i, token in enumerate(a, 1):
        next_row = [i]
        for j, other in enumerate(b, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1,
                                row[j - 1] + (token != other)))
        row = next_row
    return row[-1] / len(a) if a else None


key = Path(sys.argv[1]).read_text(encoding="utf-8-sig").strip()
if key.startswith("GNANI_API_KEY="):
    key = key.split("=", 1)[1].strip()
if not key or "\n" in key or "\r" in key:
    raise SystemExit("Invalid key file")
client = GnaniClient(api_key=key)
cases = [
    ("en", "en-IN", "Overfitting means a model memorizes training examples and performs poorly on new data."),
    ("te", "te-IN", "ఓవర్‌ఫిట్టింగ్ అంటే శిక్షణ డేటాపై బాగా పనిచేసి కొత్త డేటాపై తప్పులు చేయడం."),
    ("hi", "hi-IN", "ओवरफिटिंग में मॉडल प्रशिक्षण डेटा याद रखता है लेकिन नए डेटा पर गलतियां करता है।"),
    ("te_en_mix", "te-IN", "ఓవర్‌ఫిట్టింగ్ అంటే training data మీద accuracy ఎక్కువ, కానీ new data మీద performance తక్కువ."),
]
results = []
for name, language, reference in cases:
    case = {"id": name, "tts_language": language, "reference": reference,
            "source": "Gnani Timbre v2.5 synthetic speech", "stt": []}
    start = time.perf_counter()
    try:
        audio = client.synthesize(reference, language)
        case["tts_ms"] = round((time.perf_counter() - start) * 1000, 1)
        case["audio_bytes"] = len(audio)
    except GnaniError as exc:
        case["tts_error"] = str(exc)
        results.append(case)
        continue
    for model, hint in [("prisma-v2.5", language), ("prisma-v3.0", "indic-auto")]:
        start = time.perf_counter()
        item = {"model_requested": model, "language_hint": hint}
        try:
            response = client.transcribe(audio, hint, model_version=model)
            item.update({"elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
                         "model_reported": response["model"],
                         "detected_language_code": response["detected_language_code"],
                         "transcript": response["transcript"],
                         "raw_token_edit_rate_vs_tts_input": round(wer(reference, response["transcript"]), 3)})
        except GnaniError as exc:
            item.update({"elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
                         "error": str(exc)})
        case["stt"].append(item)
    results.append(case)

report = {"run_type": "live_gnani_synthetic_speech_smoke", "cases": results,
          "caveat": "TTS input is only a proxy reference; pronunciation and script may differ. No human ASR labels or real candidate audio."}
Path(sys.argv[2]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"cases": len(results), "tts_successes": sum("tts_ms" in c for c in results),
                  "stt_successes": sum("transcript" in s for c in results for s in c["stt"]),
                  "report": sys.argv[2]}))



