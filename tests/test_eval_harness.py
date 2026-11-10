"""Offline functional/regression checks for the scoring experiment infrastructure."""
import copy
import json
import math

import httpx
import pytest

from coach import evaluate
from eval_harness.harness import (compare_baseline, fingerprint, load_dataset,
                                  run_evaluation)
from eval_harness.ollama_judge import ollama_score

DATASET = "eval_harness/datasets/practice_review_queue.json"


def one_case_dataset():
    data = load_dataset(DATASET)
    return {**data, "cases": data["cases"][:1]}


def test_synthetic_cases_have_no_claimed_human_gold():
    data = load_dataset(DATASET)
    assert len(data["cases"]) >= 8
    assert all(c["review_status"] == "unreviewed" and c["reference"] is None for c in data["cases"])
    report = run_evaluation(data, repeats=3)
    assert report["summary"]["total_scoring_calls"] == 3 * len(data["cases"])
    assert report["summary"]["mae_to_human"] is None
    assert report["summary"]["dimension_mae_to_human"] is None
    assert report["summary"]["max_within_case_score_std"] == 0
    assert all(c["human_reference"] is None for c in report["cases"])


def test_stable_heuristic_is_repeatable_and_does_not_claim_llm_accuracy():
    report = run_evaluation(one_case_dataset(), repeats=5)
    assert report["summary"]["mean_within_case_score_std"] == 0.0
    assert "Deterministic heuristic" in report["limitations"][1]
    assert report["cases"][0]["score_std"] == 0
    assert report["cases"][0]["latency_ms"]["p95_nearest_rank"] >= 0


def test_detects_non_deterministic_scorer():
    data = one_case_dataset()
    i = 0

    def variable_scorer(*args):
        nonlocal i
        result = copy.deepcopy(evaluate(*args))
        result["dimensions"]["clarity"] -= (i % 2) * 1
        result["score"] = sum(result["dimensions"].values())
        i += 1
        return result

    report = run_evaluation(data, repeats=4, scorer=variable_scorer)
    assert report["cases"][0]["score_std"] == pytest.approx(0.5)
    assert report["cases"][0]["dimensions"]["clarity"]["std"] == pytest.approx(0.5)


def test_comparison_detects_per_dimension_drift_even_if_total_unchanged():
    baseline = run_evaluation(one_case_dataset(), repeats=2)
    changed = copy.deepcopy(baseline)
    first = changed["cases"][0]
    first["dimensions"]["relevance"]["mean"] -= 1
    first["dimensions"]["evidence"]["mean"] += 1
    comparison = compare_baseline(changed, baseline)
    assert not comparison["passed"]
    assert comparison["regressed_cases"][0]["score_delta"] == 0


def test_comparison_rejects_changed_data_and_catches_total_drift():
    data = one_case_dataset()
    baseline = run_evaluation(data, repeats=2)
    changed = copy.deepcopy(baseline)
    changed["cases"][0]["mean_score"] += 2
    assert not compare_baseline(changed, baseline, max_absolute_score_drift=1)["passed"]
    assert compare_baseline(changed, baseline, max_absolute_score_drift=2)["passed"]
    changed["dataset_sha256"] = "different"
    with pytest.raises(ValueError, match="fingerprint"):
        compare_baseline(changed, baseline)


def test_rejects_unreviewed_case_with_claimed_gold(tmp_path):
    data = one_case_dataset()
    data["cases"][0]["reference"] = {"score": 25}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Unreviewed"):
        load_dataset(path)
    with pytest.raises(ValueError, match="Unreviewed"):
        run_evaluation(data)


def test_human_reviewed_score_measures_mae_and_bias():
    data = one_case_dataset()
    case = data["cases"][0]
    result = evaluate(case["answer"], __import__("coach").QUESTION_BANK[case["track"]][case["question_index"]],
                      case["language"], case["track"], case["question_index"])
    case["review_status"] = "human_reviewed"
    case["reference"] = {"reviewer_id": "sample-rater-not-real", "rubric_version": "practice-v1",
                         "score": result["score"], "dimensions": result["dimensions"].copy()}
    report = run_evaluation(data, repeats=2)
    assert report["summary"]["human_reviewed_cases"] == 1
    assert report["summary"]["mae_to_human"] == 0
    assert report["summary"]["signed_bias_to_human"] == 0
    assert report["summary"]["dimension_mae_to_human"]["relevance"] == 0


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, 50])
def test_invalid_scores_fail_closed(invalid):
    def bad(*args):
        return {"score": invalid, "dimensions": {
            "relevance": 0, "technical_coverage": 0, "clarity": 0, "evidence": 0}}
    with pytest.raises(ValueError):
        run_evaluation(one_case_dataset(), 2, bad)


def test_ollama_judge_validates_response(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "test-local-model")
    requested = []

    def fake_post(url, *, json, timeout):
        requested.append({"url": url, "json": json})
        req = httpx.Request("POST", url)
        response = {"message": {"content": '{"dimensions": {"relevance": 10, '
                       '"technical_coverage": 15, "clarity": 10, "evidence": 5}}'}}
        return httpx.Response(200, request=req, json=response)

    monkeypatch.setattr(httpx, "post", fake_post)
    from coach import QUESTION_BANK
    result = ollama_score("A concise answer", QUESTION_BANK["ai"][0], "en-IN", "ai", 0)
    assert result["score"] == 40
    assert requested[0]["json"]["options"]["temperature"] == 0
    assert "test-local-model" in requested[0]["json"]["model"]


def test_ollama_judge_rejects_malformed_and_out_of_range(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "test-local-model")
    def bad_post(url, *, json, timeout):
        req = httpx.Request("POST", url)
        return httpx.Response(200, request=req, json={"message": {"content": '{"dimensions": {"relevance": 999, '
                            '"technical_coverage": 15, "clarity": 10, "evidence": 5}}'}})
    monkeypatch.setattr(httpx, "post", bad_post)
    from coach import QUESTION_BANK
    with pytest.raises(ValueError):
        ollama_score("Content", QUESTION_BANK["ai"][0], "en-IN", "ai", 0)


def test_duplicate_case_rejected():
    data = one_case_dataset()
    data["cases"].append(copy.deepcopy(data["cases"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        run_evaluation(data)


def test_fingerprint_is_order_independent_for_dict_keys():
    d = one_case_dataset()
    reordered = {"cases": d["cases"], "dataset_id": d["dataset_id"], "purpose": d["purpose"]}
    assert fingerprint(d) == fingerprint(reordered)
