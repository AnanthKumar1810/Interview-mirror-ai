"""Evaluate scoring stability, calibration (when adjudicated), and regression drift.

Candidate answers are treated as data. No reference score is inferred from
lexical coverage or generated from the system being evaluated.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from collections.abc import Callable
from pathlib import Path

from coach import QUESTION_BANK, evaluate
from evaluation import DIMENSION_MAX

Scorer = Callable[[str, dict, str, str, int], dict]


def fingerprint(dataset: dict) -> str:
    canonical = json.dumps(dataset, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_dataset(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list) or not data["cases"]:
        raise ValueError("Dataset must contain a nonempty 'cases' array")
    ids = set()
    for case in data["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Each case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in ids:
            raise ValueError("Case IDs must be unique, nonempty strings")
        ids.add(case_id)
        track, index, language = case.get("track"), case.get("question_index"), case.get("language")
        if track not in QUESTION_BANK or type(index) is not int or not 0 <= index < len(QUESTION_BANK[track]):
            raise ValueError(f"Invalid track/question_index for {case_id}")
        if language not in ("en-IN", "te-IN", "hi-IN"):
            raise ValueError(f"Unsupported language for {case_id}")
        if not isinstance(case.get("answer"), str) or not case["answer"].strip():
            raise ValueError(f"Missing answer for {case_id}")
        reviewed = case.get("review_status", "unreviewed")
        if reviewed not in ("unreviewed", "human_reviewed"):
            raise ValueError(f"Invalid review status for {case_id}")
        reference = case.get("reference")
        if reviewed == "unreviewed" and reference is not None:
            raise ValueError(f"Unreviewed case {case_id} cannot have a reference score")
        if reviewed == "human_reviewed":
            if not isinstance(reference, dict) or not str(reference.get("reviewer_id", "")).strip():
                raise ValueError(f"Human-reviewed case {case_id} needs a reference and reviewer ID")
            if not str(reference.get("rubric_version", "")).strip():
                raise ValueError(f"Human-reviewed case {case_id} needs rubric_version")
            _validate_dimensions(reference.get("dimensions"))
            if reference.get("score") != sum(reference["dimensions"].values()):
                raise ValueError(f"Reference total does not equal dimension sum for {case_id}")
    return data


def _validate_dimensions(dimensions: object) -> None:
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSION_MAX):
        raise ValueError("Dimensions must match the declared rubric exactly")
    for name, cap in DIMENSION_MAX.items():
        value = dimensions[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= cap:
            raise ValueError(f"Invalid dimension {name}: expected finite number in 0..{cap}")


def _validate_result(result: object) -> None:
    if not isinstance(result, dict):
        raise ValueError("Scorer must return a dictionary")
    _validate_dimensions(result.get("dimensions"))
    score = result.get("score")
    if isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score):
        raise ValueError("Score must be finite numeric")
    if abs(score - sum(result["dimensions"].values())) > 1e-6:
        raise ValueError("Score does not equal the sum of dimension scores")


def _p95(values: list[float]) -> float:
    # Nearest-rank p95; useful for explaining latency percentiles.
    return sorted(values)[math.ceil(len(values) * 0.95) - 1]


def run_evaluation(data: dict, repeats: int = 5, scorer: Scorer = evaluate,
                   scorer_name: str = "transcript_heuristic_v2") -> dict:
    if type(repeats) is not int or not 2 <= repeats <= 100:
        raise ValueError("repeats must be an integer between 2 and 100")
    # Validate in memory too, not only data loaded from disk.
    # Reuse the same schema checker via a small internal validator without writing files.
    _validate_in_memory(data)
    cases = []
    for c in data["cases"]:
        question = QUESTION_BANK[c["track"]][c["question_index"]]
        results, latencies = [], []
        for _ in range(repeats):
            start = time.perf_counter()
            result = scorer(c["answer"], question, c["language"], c["track"], c["question_index"])
            elapsed_ms = (time.perf_counter() - start) * 1000
            _validate_result(result)
            latencies.append(elapsed_ms)
            results.append(result)
        scores = [float(r["score"]) for r in results]
        dimensions = {
            name: {"mean": statistics.mean(float(r["dimensions"][name]) for r in results),
                   "std": statistics.pstdev(float(r["dimensions"][name]) for r in results)}
            for name in DIMENSION_MAX
        }
        item = {"id": c["id"], "track": c["track"], "language": c["language"],
                "review_status": c.get("review_status", "unreviewed"),
                "mean_score": statistics.mean(scores), "score_std": statistics.pstdev(scores),
                "min_score": min(scores), "max_score": max(scores),
                "dimensions": dimensions,
                "latency_ms": {"mean": statistics.mean(latencies), "p95_nearest_rank": _p95(latencies)},
                "human_reference": None}
        if c.get("review_status") == "human_reviewed":
            ref = c["reference"]
            item["human_reference"] = {
                "score": ref["score"], "signed_error": item["mean_score"] - ref["score"],
                "absolute_error": abs(item["mean_score"] - ref["score"]),
                "dimension_absolute_errors": {
                    d: abs(dimensions[d]["mean"] - ref["dimensions"][d]) for d in DIMENSION_MAX
                },
                "rubric_version": ref["rubric_version"],
            }
        cases.append(item)
    reviewed = [c for c in cases if c["human_reference"] is not None]
    summary = {
        "n_cases": len(cases), "repeat_count": repeats,
        "total_scoring_calls": len(cases) * repeats,
        "mean_within_case_score_std": statistics.mean(c["score_std"] for c in cases),
        "max_within_case_score_std": max(c["score_std"] for c in cases),
        "human_reviewed_cases": len(reviewed),
        "mae_to_human": statistics.mean(c["human_reference"]["absolute_error"] for c in reviewed) if reviewed else None,
        "signed_bias_to_human": statistics.mean(c["human_reference"]["signed_error"] for c in reviewed) if reviewed else None,
        "dimension_mae_to_human": {
            d: statistics.mean(c["human_reference"]["dimension_absolute_errors"][d] for c in reviewed)
            for d in DIMENSION_MAX
        } if reviewed else None,
    }
    return {"schema_version": 1, "dataset_id": data.get("dataset_id", "unnamed"),
            "dataset_sha256": fingerprint(data), "scorer_name": scorer_name,
            "summary": summary, "cases": cases,
            "limitations": [
                "No accuracy or bias conclusion without adequately adjudicated human references.",
                "Deterministic heuristic repeats do not establish stochastic LLM scorer reliability.",
                "Measured durations are local scorer-call wall times, not end-to-end STT/LLM/TTS latency.",
            ]}


def _validate_in_memory(data: dict) -> None:
    # Keep one authoritative schema checker for in-memory and file-based datasets.
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list) or not data["cases"]:
        raise ValueError("Dataset must contain a nonempty cases list")
    # Validation mirrors the loader without serializing or modifying the original data.
    ids = set()
    for c in data["cases"]:
        if not isinstance(c, dict): raise ValueError("Expected object in cases")
        case_id = c.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError("Duplicate/missing case ID")
        ids.add(case_id)
        t, i, l = c.get("track"), c.get("question_index"), c.get("language")
        if t not in QUESTION_BANK or type(i) is not int or not 0 <= i < len(QUESTION_BANK[t]) or l not in ("en-IN", "te-IN", "hi-IN"):
            raise ValueError(f"Invalid question metadata: {case_id}")
        if not isinstance(c.get("answer"), str) or not c["answer"].strip():
            raise ValueError(f"Invalid answer: {case_id}")
        review, ref = c.get("review_status", "unreviewed"), c.get("reference")
        if review == "unreviewed":
            if ref is not None: raise ValueError(f"Unreviewed case has reference: {case_id}")
        elif review == "human_reviewed":
            if not isinstance(ref, dict) or not str(ref.get("reviewer_id", "")).strip() or not str(ref.get("rubric_version", "")).strip():
                raise ValueError(f"Incomplete human review: {case_id}")
            _validate_dimensions(ref.get("dimensions"))
            if ref.get("score") != sum(ref["dimensions"].values()):
                raise ValueError(f"Reference score disagrees with dimensions: {case_id}")
        else:
            raise ValueError(f"Invalid review status: {case_id}")


def compare_baseline(candidate: dict, baseline: dict, max_absolute_score_drift: float = 0.0) -> dict:
    if max_absolute_score_drift < 0 or not math.isfinite(max_absolute_score_drift):
        raise ValueError("max_absolute_score_drift must be nonnegative")
    if candidate["dataset_sha256"] != baseline.get("dataset_sha256"):
        raise ValueError("Dataset fingerprint changed; cannot compare these runs")
    previous = {c["id"]: c for c in baseline["cases"]}
    current = {c["id"]: c for c in candidate["cases"]}
    if previous.keys() != current.keys():
        raise ValueError("Case set changed")
    drift = []
    for case_id in sorted(current):
        before, after = previous[case_id], current[case_id]
        change = after["mean_score"] - before["mean_score"]
        dimension_deltas = {d: after["dimensions"][d]["mean"] - before["dimensions"][d]["mean"]
                            for d in DIMENSION_MAX}
        if abs(change) > max_absolute_score_drift + 1e-9 or any(abs(v) > max_absolute_score_drift + 1e-9 for v in dimension_deltas.values()):
            drift.append({"id": case_id, "score_delta": change, "dimension_deltas": dimension_deltas})
    return {"passed": not drift, "allowed_absolute_drift": max_absolute_score_drift,
            "regressed_cases": drift, "compared_cases": len(current)}
