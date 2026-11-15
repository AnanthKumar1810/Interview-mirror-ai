import json

import pytest

from eval_harness.gold_evaluation import (
    ConsentRecord,
    GoldCase,
    GoldEvaluationSet,
    ReviewerRating,
)
from eval_harness.gold_workflow import (
    export_review_forms,
    export_gnani_holdout_manifest,
    holdout_digest,
    import_review,
    load_dataset,
    validate_dataset,
)


def sample_dataset(*, pii_redacted=True):
    case = GoldCase(
        case_id="case_001",
        participant_id="participant_001",
        question_family_id="system_design_01",
        question_text="How would you design a rate limiter?",
        reference_answer="Use a token bucket and explain distributed state.",
        candidate_answer="I would use a token bucket and a shared store.",
        domain="backend",
        language="en-IN",
        split="locked_test_holdout",
        consent=ConsentRecord(True, "consent-v1", "2026-11-15T10:00:00Z"),
        pii_redacted=pii_redacted,
    )
    return GoldEvaluationSet(cases=[case])


def rating(reviewer_id):
    return {
        "timestamp_utc": "2026-11-15T11:00:00Z",
        "dimensions": {
            "concept_coverage": 25,
            "relevance_completeness": 20,
            "clarity_coherence": 15,
            "evidence_tradeoffs": 10,
        },
        "total_score": 70,
        "verdict": "partial",
        "evidence_quotes": ["token bucket"],
        "rationale": f"Reviewed independently by {reviewer_id}.",
    }


def test_empty_archive_template_reports_zero_gold():
    from pathlib import Path

    template = Path(__file__).parents[1] / "eval_harness" / "datasets" / "gold_holdout_template.json"
    dataset = load_dataset(template)
    result = validate_dataset(dataset)
    assert result["status"] == "incomplete"
    assert result["gold_examples_count"] == 0
    assert result["total_cases"] == 0


def test_review_forms_are_separate_and_content_bound(tmp_path):
    dataset = sample_dataset()
    review_count = export_review_forms(dataset, ["reviewer_a", "reviewer_b"], tmp_path)
    assert review_count == 2
    forms = [tmp_path / reviewer / "review.json" for reviewer in ("reviewer_a", "reviewer_b")]
    for form_path in forms:
        form = json.loads(form_path.read_text(encoding="utf-8"))
        assert len(form["cases"]) == 1
        assert form["cases"][0]["rating"] is None
        form["cases"][0]["rating"] = rating(form["reviewer_id"])
        form_path.write_text(json.dumps(form), encoding="utf-8")
        assert import_review(dataset, form_path) == 1
    assert validate_dataset(dataset)["pending_review_cases"] == 0

    dataset.status = "adjudicated_ready"
    dataset.holdout_sha256 = holdout_digest(dataset)
    assert validate_dataset(dataset)["gold_examples_count"] == 1
    dataset.cases[0].candidate_answer += " changed"
    with pytest.raises(ValueError, match="digest"):
        validate_dataset(dataset)


def test_gold_export_fails_without_pii_redaction(tmp_path):
    with pytest.raises(ValueError, match="PII"):
        export_review_forms(sample_dataset(pii_redacted=False), ["reviewer_a", "reviewer_b"], tmp_path)


def test_reviewer_rating_rejects_nonfinite_dimension():
    item = rating("reviewer_a")
    item["dimensions"]["concept_coverage"] = float("nan")
    with pytest.raises(ValueError, match="out of bounds"):
        ReviewerRating(reviewer_id="reviewer_a", **item).validate("token bucket")


def test_gnani_manifest_export_requires_sealed_human_holdout(tmp_path):
    dataset = sample_dataset()
    for reviewer_id in ("reviewer_a", "reviewer_b"):
        dataset.cases[0].reviewers.append(ReviewerRating(reviewer_id=reviewer_id, **rating(reviewer_id)))
    dataset.status = "adjudicated_ready"
    dataset.holdout_sha256 = holdout_digest(dataset)
    output = tmp_path / "private_manifest.json"
    assert export_gnani_holdout_manifest(dataset, output) == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    case = manifest["cases"][0]
    assert case["label"] == 70
    assert case["reviewer_ids"] == ["reviewer_a", "reviewer_b"]
    assert case["dataset"] == "fresh_mixed_holdout"


def test_gnani_manifest_export_rejects_unsealed_dataset(tmp_path):
    with pytest.raises(ValueError, match="sealed"):
        export_gnani_holdout_manifest(sample_dataset(), tmp_path / "manifest.json")
