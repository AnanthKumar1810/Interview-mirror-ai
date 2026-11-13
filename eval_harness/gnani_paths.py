"""Offline validation and optional live Gnani Evon A/B/C benchmark.

Input JSON is a local, rights-cleared manifest; this tool never downloads data.
All three paths use the same transcript and the same Evon evaluator.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from gnani_semantic import Case, LocalEvon, evaluate_paths


def validate_manifest(data: dict) -> list[dict]:
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Manifest needs nonempty cases")
    seen = set()
    groups = defaultdict(set)
    for case in cases:
        required = ("id", "dataset", "split", "person_id", "variant_group_id",
                    "question", "reference", "transcript", "label_kind")
        if any(not isinstance(case.get(k), str) or not case[k].strip() for k in required):
            raise ValueError(f"Missing required case field: {case.get('id', '?')}")
        if case["id"] in seen:
            raise ValueError("Duplicate case id")
        seen.add(case["id"])
        if case["split"] not in {"development", "test"}:
            raise ValueError("split must be development or test")
        groups[(case["dataset"], "person", case["person_id"])].add(case["split"])
        groups[(case["dataset"], "variant", case["variant_group_id"])].add(case["split"])
        if case["label_kind"] not in {"none", "numeric", "categorical"}:
            raise ValueError("Unsupported label kind")
        if case["label_kind"] == "numeric":
            if (not isinstance(case.get("label"), (int, float)) or isinstance(case.get("label"), bool)
                    or not isinstance(case.get("label_max"), (int, float))
                    or not 0 <= case["label"] <= case["label_max"] or case["label_max"] <= 0):
                raise ValueError("Invalid native numeric label")
        if case["label_kind"] == "categorical":
            if not isinstance(case.get("label"), str) or not isinstance(case.get("label_namespace"), str):
                raise ValueError("Categorical label and original label namespace are required")
        if case["dataset"] == "fresh_mixed_holdout":
            if (case["split"] != "test" or case["label_kind"] == "none"
                    or len(set(case.get("reviewer_ids", []))) < 2
                    or not case.get("consent_recorded")):
                raise ValueError("Fresh holdout requires consent and two independent reviewers")
    if any(len(splits) > 1 for splits in groups.values()):
        raise ValueError("Person or translation/paraphrase family leaks across splits")
    return cases


def summarize(cases: list[dict], results: list[dict]) -> dict:
    by_id = {r["id"]: r for r in results}
    summary = {}
    for dataset in sorted({c["dataset"] for c in cases}):
        subset = [c for c in cases if c["dataset"] == dataset and c["id"] in by_id]
        entry = {"n": len(subset), "paths": {}}
        for path in ("direct", "translated", "hybrid"):
            rows = [(c, by_id[c["id"]][path]) for c in subset if by_id[c["id"]].get(path)]
            numeric = [(c, r) for c, r in rows if c["label_kind"] == "numeric" and r.get("score") is not None]
            # Only compare labels already defined in our four-way verdict space.
            # SemEval five-way or ScAA binary need a separate, explicit task adapter.
            categorical = [(c, r) for c, r in rows if c["label_kind"] == "categorical"
                           and c["label_namespace"] == "interview_verdict_4way"
                           and r.get("verdict") != "uncertain"]
            by_scale = defaultdict(list)
            for c, r in numeric:
                by_scale[c["label_max"]].append(abs(r["score"] * c["label_max"] / 10 - c["label"]))
            entry["paths"][path] = {
                "n_scored": len(rows),
                "n_abstained": sum(r.get("score") is None for _, r in rows),
                "numeric_mae_by_native_scale": {str(scale): sum(errors) / len(errors)
                                                 for scale, errors in by_scale.items()},
                "numeric_n_by_native_scale": {str(scale): len(errors) for scale, errors in by_scale.items()},
                "categorical_accuracy": (sum(c["label"] == r["verdict"] for c, r in categorical)
                                         / len(categorical) if categorical else None),
                "categorical_n": len(categorical),
                "excluded_incompatible_categorical_n": sum(
                    c["label_kind"] == "categorical"
                    and c["label_namespace"] != "interview_verdict_4way" for c, _ in rows),
                "median_latency_ms": (statistics.median(
                    by_id[c["id"]]["timing_ms"][{"direct": "direct", "translated": "translation_plus_score",
                                                   "hybrid": "hybrid_counterfactual"}[path]]
                    for c, _ in rows) if rows else None),
            }
        summary[dataset] = entry
    return summary


def run(data: dict, model: LocalEvon) -> dict:
    cases = validate_manifest(data)
    results = []
    for case in cases:
        result = evaluate_paths(Case(case["question"], case["reference"],
                                     case["transcript"], case["id"]), model)
        results.append({"id": case["id"], "direct": result["direct"],
                        "translated": result["translated"], "hybrid": result["hybrid"],
                        "timing_ms": result["timing_ms"],
                        "translated_text": result["translated_text"]})
    return {"run_type": "live_gnani_evon", "model": model.model, "results": results,
            "summary": summarize(cases, results),
            "limitations": ["Prompted Evon scoring is uncalibrated for hiring.",
                            "A/B/C share one ASR transcript; STT time must be measured separately.",
                            "Numeric MAE scales model 0–10 to each dataset's native range."]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-live", action="store_true")
    args = parser.parse_args()
    data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    cases = validate_manifest(data)
    if not args.run_live:
        print(json.dumps({"status": "manifest_validated_offline", "cases": len(cases),
                          "live_model_calls": 0}))
        return 0
    result = run(data, LocalEvon())
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "live_complete", "cases": len(cases)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

