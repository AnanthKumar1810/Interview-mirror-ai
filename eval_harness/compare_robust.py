"""Compare baseline and risk-aware scorer without inventing human accuracy.

The nine-case corpus is entirely unreviewed/synthetic. Selected risk-control IDs
are developer-authored *behavioural probes*, NOT gold human scores. Any split
below is an explicit diagnostic split, not an untouched real-world test set.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from coach import evaluate
from robust_evaluation import evaluate_robust
from eval_harness.harness import load_dataset, run_evaluation

SYNTHETIC_RISK_IDS = {"agentic_en_keyword_stuffing", "ai_en_false_claim"}
DEV_IDS = {"agentic_en_strong", "agentic_en_empty", "agentic_en_keyword_stuffing",
           "agentic_te_terms", "software_hi_short"}
THRESHOLD = 70


def comparison(data: dict) -> dict:
    baseline = run_evaluation(data, repeats=5, scorer=evaluate,
                              scorer_name="transcript_heuristic_v2")
    improved = run_evaluation(data, repeats=5, scorer=evaluate_robust,
                              scorer_name="risk_aware_rubric_v3")
    old = {c["id"]: c for c in baseline["cases"]}
    new = {c["id"]: c for c in improved["cases"]}
    cases = [{"id": case_id, "split": "diagnostic_dev" if case_id in DEV_IDS else "diagnostic_heldout",
              "baseline_score": before["mean_score"], "improved_score": new[case_id]["mean_score"],
              "delta": new[case_id]["mean_score"] - before["mean_score"],
              "review_status": new[case_id]["review_status"]}
             for case_id, before in old.items()]
    actual_risk_cases = SYNTHETIC_RISK_IDS.intersection(old)
    false_high_before = sum(old[c]["mean_score"] >= THRESHOLD for c in actual_risk_cases)
    false_high_after = sum(new[c]["mean_score"] >= THRESHOLD for c in actual_risk_cases)
    failures = []
    if not actual_risk_cases:
        failures.append("Missing synthetic risk-control cases")
    if false_high_after:
        failures.append("Improved scorer gave a high grade to a known synthetic risk-control case")
    if improved["summary"]["max_within_case_score_std"]:
        failures.append("Unexpected variation in deterministic evaluator")
    return {"dataset_id": data["dataset_id"], "dataset_sha256": improved["dataset_sha256"],
            "n_cases": len(cases), "n_human_reviewed": improved["summary"]["human_reviewed_cases"],
            "human_mae": improved["summary"]["mae_to_human"], "diagnostic_split": {
                "dev_ids": sorted(DEV_IDS.intersection(old)),
                "heldout_ids": sorted(set(old) - DEV_IDS),
                "warning": "Split defined for reproducibility but the tiny synthetic corpus has already been inspected. This is not blinded generalization evidence."
            },
            "synthetic_risk_probes": {"ids": sorted(actual_risk_cases), "high_score_threshold": THRESHOLD,
                                      "baseline_high_scores": false_high_before,
                                      "improved_high_scores": false_high_after,
                                      "total_probes": len(actual_risk_cases)},
            "stability": {"baseline_max_std": baseline["summary"]["max_within_case_score_std"],
                          "improved_max_std": improved["summary"]["max_within_case_score_std"]},
            "cases": cases, "gate": {"passed": not failures, "failures": failures},
            "limitations": ["No human-reviewed labels: accuracy, MAE and agreement are UNMEASURABLE.",
                            "Lexical/rule-based safeguards are not general factual verification.",
                            "Measured scorer-call latency is not voice pipeline latency.",
                            "No live Gnani or local Ollama requests are made by this benchmark."]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval_harness/datasets/practice_review_queue.json")
    parser.add_argument("--output", default="reports/robust_comparison.json")
    args = parser.parse_args()
    report = comparison(load_dataset(args.dataset))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Synthetic risk high scores: {report['synthetic_risk_probes']['baseline_high_scores']}/{report['synthetic_risk_probes']['total_probes']} baseline vs {report['synthetic_risk_probes']['improved_high_scores']}/{report['synthetic_risk_probes']['total_probes']} improved")
    print(f"Human-reviewed: {report['n_human_reviewed']}; human MAE: {report['human_mae']}")
    print("PASS" if report["gate"]["passed"] else f"FAIL: {report['gate']['failures']}")
    return 0 if report["gate"]["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
