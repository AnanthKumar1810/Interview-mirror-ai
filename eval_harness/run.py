"""CLI: python -m eval_harness.run --dataset ... --output ... [--compare ...]."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_harness.harness import compare_baseline, load_dataset, run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description="InterviewMirror scoring evaluation")
    parser.add_argument("--dataset", default="eval_harness/datasets/practice_review_queue.json")
    parser.add_argument("--output", default="reports/phase1_latest.json")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--scorer", choices=("heuristic", "robust", "ollama"), default="heuristic")
    parser.add_argument("--compare", help="Baseline report for regression checking")
    parser.add_argument("--max-absolute-score-drift", type=float, default=0.0)
    parser.add_argument("--max-within-case-std", type=float, default=None)
    parser.add_argument("--require-all-human-reviewed", action="store_true")
    parser.add_argument("--max-human-mae", type=float, default=None)
    args = parser.parse_args()
    dataset = load_dataset(args.dataset)
    if args.scorer == "robust":
        from robust_evaluation import evaluate_robust
        scorer = evaluate_robust
        scorer_name = "risk_aware_rubric_v3"
    elif args.scorer == "ollama":
        from eval_harness.ollama_judge import ollama_score
        scorer = ollama_score
        import os
        scorer_name = "ollama_" + os.getenv("OLLAMA_MODEL", "not_configured")
    else:
        from coach import evaluate
        scorer = evaluate
        scorer_name = "transcript_heuristic_v2"
    report = run_evaluation(dataset, args.repeats, scorer, scorer_name)
    failures = []
    if args.compare:
        baseline = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        result = compare_baseline(report, baseline, args.max_absolute_score_drift)
        report["regression_gate"] = result
        if not result["passed"]:
            failures.append(f"regression drift on {len(result['regressed_cases'])} cases")
    if args.max_within_case_std is not None and report["summary"]["max_within_case_score_std"] > args.max_within_case_std:
        failures.append("score instability exceeds threshold")
    if args.require_all_human_reviewed and report["summary"]["human_reviewed_cases"] != report["summary"]["n_cases"]:
        failures.append("not all cases have human review")
    if args.max_human_mae is not None:
        mae = report["summary"]["mae_to_human"]
        if mae is None:
            failures.append("cannot gate on human MAE without human-reviewed reference scores")
        elif mae > args.max_human_mae:
            failures.append("human MAE exceeds threshold")
    report["gate"] = {"passed": not failures, "failures": failures}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    s = report["summary"]
    print(f"Scorer: {report['scorer_name']} | cases: {s['n_cases']} | calls: {s['total_scoring_calls']}")
    print(f"Mean within-case std: {s['mean_within_case_score_std']:.3f} | "
          f"human-reviewed: {s['human_reviewed_cases']} | human MAE: {s['mae_to_human']}")
    print(f"Report: {output} | gate: {'PASS' if not failures else 'FAIL: ' + '; '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
