import pytest

from eval_harness.import_jorgpt import convert as convert_jorgpt
from eval_harness.import_mohler import convert as convert_mohler


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


def test_mohler_preserves_both_graders_and_native_average():
    row = {"row": {"id": "E01.Q01.A00", "question": "What is a prototype?",
                   "instructor_answer": "An early model", "student_answer": "A draft program",
                   "score_grader_1": 3.0, "score_grader_2": 4.0, "score_avg": 3.5}}
    cases, skipped = convert_mohler([row])
    assert skipped == 0
    assert cases[0]["label"] == 3.5
    assert cases[0]["label_max"] == 5
    assert (cases[0]["grader_1"], cases[0]["grader_2"]) == (3.0, 4.0)

