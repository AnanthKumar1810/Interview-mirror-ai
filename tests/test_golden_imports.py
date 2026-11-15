import pytest
from pathlib import Path

from eval_harness.import_jorgpt import convert as convert_jorgpt, read as read_jorgpt
from eval_harness.import_mohler import convert as convert_mohler, load_local_rows
from eval_harness.gold_evaluation import (
    ConsentRecord,
    GoldCase,
    GoldEvaluationSet,
    ReviewerRating,
    AdjudicationRecord,
    partition_cases_grouped,
)
from gnani_semantic import LocalEvon, ProviderUnavailable


def jorgpt_row(entry, student, language="en"):
    return {"entry_id": entry, "question_id": "Q1", "question_text": "What is TDD?",
            "student_answer": ("Tests first " if language == "en" else "Pruebas primero ") + entry,
            "ideal_answer": "Write tests before implementation",
            "student_anom_id": student, "teacher_grade": "7.0",
            "teacher_corrected": "True"}


def test_jorgpt_translations_share_person_split_and_variant():
    en = [jorgpt_row(str(i), f"student-{i}") for i in range(5)]
    es = [jorgpt_row(str(i), f"student-{i}", "es") for i in range(5)]
    result = convert_jorgpt(en, es)
    assert result["n_students"] == 5
    assert result["n_test_students"] == 1
    for i in range(5):
        pair = [c for c in result["cases"] if c["variant_group_id"] == str(i)]
        assert len(pair) == 2
        assert len({c["split"] for c in pair}) == 1
        assert {c["language"] for c in pair} == {"en", "es"}


def test_jorgpt_rejects_mismatched_human_grade():
    en = [jorgpt_row("1", "person")]
    es = [jorgpt_row("1", "person", "es")]
    es[0]["teacher_grade"] = "9.0"
    with pytest.raises(ValueError, match="Paired"):
        convert_jorgpt(en, es)


def test_jorgpt_missing_file_raises_file_not_found(tmp_path):
    missing_file = tmp_path / "non_existent.csv"
    with pytest.raises(FileNotFoundError, match="not found"):
        read_jorgpt(missing_file)


def test_jorgpt_missing_required_fields_raises_error(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("entry_id,question_id\n1,Q1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        read_jorgpt(bad_csv)


def test_mohler_preserves_both_graders_and_native_average():
    row = {"row": {"id": "E01.Q01.A00", "question": "What is a prototype?",
                   "instructor_answer": "An early model", "student_answer": "A draft program",
                   "score_grader_1": 3.0, "score_grader_2": 4.0, "score_avg": 3.5}}
    cases, skipped = convert_mohler([row])
    assert skipped == 0
    assert cases[0]["label"] == 3.5
    assert cases[0]["label_max"] == 5
    assert (cases[0]["grader_1"], cases[0]["grader_2"]) == (3.0, 4.0)


def test_mohler_offline_loader(tmp_path):
    data_file = tmp_path / "mohler_sample.json"
    sample = [{"row": {"id": "1", "question": "Q?", "instructor_answer": "A", "student_answer": "B", "score_avg": 4.5, "score_grader_1": 4.0, "score_grader_2": 5.0}}]
    import json
    data_file.write_text(json.dumps(sample), encoding="utf-8")
    rows = load_local_rows(data_file)
    assert len(rows) == 1
    cases, skipped = convert_mohler(rows)
    assert len(cases) == 1
    assert cases[0]["label"] == 4.5


def test_gold_holdout_requires_two_independent_reviewers():
    consent = ConsentRecord(consented=True, consent_form_version="2026.1", timestamp_utc="2026-11-15T00:00:00Z")
    r1 = ReviewerRating(
        reviewer_id="rev_1",
        timestamp_utc="2026-11-15T01:00:00Z",
        dimensions={"concept_coverage": 30, "relevance_completeness": 20, "clarity_coherence": 15, "evidence_tradeoffs": 15},
        total_score=80.0,
        verdict="correct",
        evidence_quotes=["used asyncio"],
        rationale="Solid answer",
    )
    # Only 1 reviewer supplied
    case = GoldCase(
        case_id="case_001",
        participant_id="candidate_123",
        question_family_id="qfam_async",
        question_text="How did you use asyncio?",
        reference_answer="Used asyncio with asyncpg pool.",
        candidate_answer="I used asyncio with an async connection pool to avoid blocking.",
        domain="software",
        language="en-IN",
        split="locked_test_holdout",
        consent=consent,
        reviewers=[r1],
    )
    with pytest.raises(ValueError, match="Requires at least 2 independent human reviewers"):
        case.validate()


def test_gold_holdout_requires_adjudication_on_disagreement():
    consent = ConsentRecord(consented=True, consent_form_version="2026.1", timestamp_utc="2026-11-15T00:00:00Z")
    answer = "I used asyncio with an async connection pool to avoid blocking."
    r1 = ReviewerRating(
        reviewer_id="rev_1",
        timestamp_utc="2026-11-15T01:00:00Z",
        dimensions={"concept_coverage": 30, "relevance_completeness": 20, "clarity_coherence": 15, "evidence_tradeoffs": 15},
        total_score=80.0,
        verdict="correct",
        evidence_quotes=["used asyncio"],
        rationale="Good explanation",
    )
    r2 = ReviewerRating(
        reviewer_id="rev_2",
        timestamp_utc="2026-11-15T01:10:00Z",
        dimensions={"concept_coverage": 15, "relevance_completeness": 10, "clarity_coherence": 10, "evidence_tradeoffs": 5},
        total_score=40.0,  # Delta is 40 points (> 15 points threshold)
        verdict="partial",
        evidence_quotes=["avoid blocking"],
        rationale="Lacks trade-off details",
    )
    case = GoldCase(
        case_id="case_002",
        participant_id="candidate_123",
        question_family_id="qfam_async",
        question_text="How did you use asyncio?",
        reference_answer="Used asyncio with asyncpg pool.",
        candidate_answer=answer,
        domain="software",
        language="en-IN",
        split="locked_test_holdout",
        consent=consent,
        reviewers=[r1, r2],
    )
    # Fails without adjudication
    with pytest.raises(ValueError, match="requires formal adjudication"):
        case.validate()

    # Passes with adjudication
    case.adjudication = AdjudicationRecord(
        adjudicator_id="adjudicator_prime",
        timestamp_utc="2026-11-15T02:00:00Z",
        resolved_dimensions={"concept_coverage": 25, "relevance_completeness": 18, "clarity_coherence": 14, "evidence_tradeoffs": 10},
        resolved_score=67.0,
        resolved_verdict="partial",
        resolution_rationale="Candidate demonstrated core syntax but omitted pool failure modes.",
    )
    case.validate()


def test_gold_grouped_split_prevents_leakage():
    entries = [
        {"id": "1", "participant_id": "alice", "question_family_id": "q1"},
        {"id": "2", "participant_id": "alice", "question_family_id": "q2"},
        {"id": "3", "participant_id": "bob", "question_family_id": "q3"},
        {"id": "4", "participant_id": "bob", "question_family_id": "q4"},
        {"id": "5", "participant_id": "carol", "question_family_id": "q1"},  # Linked to alice via q1
    ]
    partitioned = partition_cases_grouped(entries, test_ratio=0.3, calibration_ratio=0.2)
    # Check that alice and carol (connected via q1) share the exact same split
    alice_splits = {e["split"] for e in partitioned if e["participant_id"] == "alice"}
    carol_splits = {e["split"] for e in partitioned if e["participant_id"] == "carol"}
    assert len(alice_splits) == 1
    assert len(carol_splits) == 1
    assert alice_splits == carol_splits


def test_honest_blocked_evon_provider():
    # Without local Gnani Evon server, LocalEvon fails closed with ProviderUnavailable
    with pytest.raises(ProviderUnavailable, match="Configure a local Evon v3.3 server URL"):
        LocalEvon(base_url="")

    # Foreign URL is rejected
    with pytest.raises(ProviderUnavailable, match="Configure a local Evon v3.3 server URL"):
        LocalEvon(base_url="https://api.openai.com")


