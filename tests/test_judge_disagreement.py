import pytest
from eval_harness.judge_disagreement import compare_judge


def test_conflicting_judge_score_is_audited_without_overriding_rubric():
    answer = "I used a test set to measure accuracy and then fixed the model."
    question = {"text": "How did you evaluate your model?", "concepts": [
        ("evaluation", ["accuracy"]), ("validation", ["test set"])]}
    report = compare_judge(answer, question, "en", lambda *args: {
        "score": 95, "quote": "test set", "reason": "Mentions a test set"})
    assert report["judge_score"] == 95
    assert report["practice_score"] != 95
    assert report["status"] == "review_required"
    assert report["difference"] == 95 - report["practice_score"]


def test_judge_cannot_invent_evidence():
    with pytest.raises(ValueError, match="exact answer text"):
        compare_judge("I tested it.", {"text": "How?"}, "en", lambda *args: {
            "score": 80, "quote": "I achieved 99% accuracy"})

