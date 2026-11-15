"""Verification of Task 5: Adaptive Evaluation Fidelity, Adversarial Probing & Corrections."""
import pytest
from coach import QUESTION_BANK, evaluate
from robust_evaluation import evaluate_robust


def test_rubric_distinguishes_correctness_unsupported_claims_and_incomplete_reasoning():
    q = QUESTION_BANK["ai"][1]

    # 1. Strong, complete answer with evidence
    complete_ans = (
        "I evaluated the model using precision and recall on a held-out validation set. "
        "Because of class imbalance, precision was 88% and recall was 82%. "
        "We tuned the decision threshold to balance false positives against false negatives."
    )
    res_complete = evaluate(complete_ans, q, "en-IN", "ai", 1)
    assert res_complete["score"] >= 65
    assert res_complete["four_dimension_rubric"]["technical_accuracy"]["score"] >= 20
    assert res_complete["four_dimension_rubric"]["project_evidence"]["score"] >= 15
    assert res_complete["four_dimension_rubric"]["design_tradeoffs"]["score"] >= 15

    # 2. Unsupported perfection claim (detected and constrained)
    unsupported_ans = (
        "I evaluated precision and recall and achieved 100 percent accuracy, "
        "which means the model will never make another mistake."
    )
    res_unsupported = evaluate_robust(unsupported_ans, q, "en-IN", "ai", 1)
    assert any(flag["code"] == "absolute_perfection_claim" for flag in res_unsupported["risk_flags"])
    # Score constrained due to ungrounded perfection claim
    assert res_unsupported["score"] < res_complete["score"]

    # 3. Incomplete reasoning without causal explanations
    incomplete_ans = "Model data test."
    res_incomplete = evaluate(incomplete_ans, q, "en-IN", "ai", 1)
    assert res_incomplete["score"] < 35
    assert res_incomplete["four_dimension_rubric"]["design_tradeoffs"]["score"] == 0


def test_adversarial_keyword_stuffing_cannot_cheat_rubric():
    q = QUESTION_BANK["agentic"][0]

    # Adversarial repetition of high-value technical keywords
    stuffing = "agent tool approval permission guardrail " * 20
    robust = evaluate_robust(stuffing, q, "en-IN", "agentic", 0)
    assert any(flag["code"] in ("keyword_stuffing", "disconnected_keyword_list") for flag in robust["risk_flags"])
    # Constrained scores
    assert robust["dimensions"]["technical_coverage"] <= 10
    assert robust["dimensions"]["evidence"] <= 3
    assert robust["score"] < 50


def test_uncalibrated_practice_guidance_disclaimers():
    q = QUESTION_BANK["software"][0]
    res = evaluate("I debugged a timeout error and fixed it.", q, "en-IN", "software", 0)
    assert res["rubric_type"] == "uncalibrated_practice_guidance"
    assert "not a hiring" in res["disclaimer"].lower() or "indicative" in res["disclaimer"].lower()
    assert res["factual_assessment"] == "not_verified"
