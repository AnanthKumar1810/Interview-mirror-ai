"""Prepare JorGPT v3 CC BY 4.0 human grades, grouped by real student ID.

Input CSVs must be downloaded from https://zenodo.org/records/18981627.
Ignore all model-generated grade columns. Spanish is opt-in and out of Evon's
documented supported languages; paired entries always share a variant group.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from eval_harness.gnani_paths import validate_manifest


def read(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"JorGPT source CSV not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required_fields = {"entry_id", "question_id", "question_text", "student_answer",
                           "ideal_answer", "student_anom_id", "teacher_grade"}
        if not reader.fieldnames or not required_fields.issubset(set(reader.fieldnames)):
            missing = required_fields - set(reader.fieldnames or [])
            raise ValueError(f"JorGPT CSV missing required fields: {sorted(missing)}")
        return list(reader)


def convert(en: list[dict], es: list[dict] | None = None) -> dict:
    en_by_id = {row["entry_id"]: row for row in en}
    if len(en_by_id) != len(en):
        raise ValueError("Duplicate English entry IDs")
    if es is not None:
        es_by_id = {row["entry_id"]: row for row in es}
        if set(es_by_id) != set(en_by_id):
            raise ValueError("English and Spanish entry IDs differ")
        for id, row in en_by_id.items():
            other = es_by_id[id]
            if (row["student_anom_id"], row["question_id"], row["teacher_grade"]) != (
                other["student_anom_id"], other["question_id"], other["teacher_grade"]):
                raise ValueError("Paired translations disagree on identity, question or teacher grade")
    students = sorted({row["student_anom_id"] for row in en if row["student_anom_id"]})
    if not students:
        raise ValueError("Missing student identities")
    # Stable person-disjoint 20% test split; keep original paired languages together.
    ordered = sorted(students, key=lambda x: hashlib.sha256(x.encode()).hexdigest())
    test_students = set(ordered[:max(1, round(len(students) * 0.2))])
    cases = []
    skipped = 0
    for language, rows in [("en", en), ("es", es)]:
        if rows is None:
            continue
        for row in rows:
            if not all(row.get(k, "").strip() for k in (
                "entry_id", "question_id", "question_text", "student_answer",
                "ideal_answer", "student_anom_id", "teacher_grade")):
                skipped += 1
                continue
            grade = float(row["teacher_grade"])
            if not 0 <= grade <= 10:
                raise ValueError("Invalid teacher grade")
            cases.append({"id": f"jorgpt:{row['entry_id']}:{language}", "dataset": "jorgpt",
                          "split": "test" if row["student_anom_id"] in test_students else "development",
                          "person_id": row["student_anom_id"],
                          "variant_group_id": row["entry_id"],
                          "question": row["question_text"].strip(),
                          "reference": row["ideal_answer"].strip(),
                          "transcript": row["student_answer"].strip(),
                          "label_kind": "numeric", "label": grade, "label_max": 10,
                          "language": language, "question_id": row["question_id"],
                          "teacher_corrected": row["teacher_corrected"]})
    def pair(case: dict) -> tuple[str, str]:
        return (" ".join(case["question"].casefold().split()),
                " ".join(case["transcript"].casefold().split()))
    test_pairs = {pair(case) for case in cases if case["split"] == "test"}
    # Some students supplied identical short answers to the same public question.
    # Keep the test rows and remove both language variants of a conflicting dev row.
    dropped_entries = {case["variant_group_id"] for case in cases
                       if case["split"] == "development" and pair(case) in test_pairs}
    cases = [case for case in cases if not (case["split"] == "development"
                                           and case["variant_group_id"] in dropped_entries)]
    data = {"dataset_id": "jorgpt", "source": "Zenodo record 18981627 v3",
            "license_declared": "CC BY 4.0", "n_students": len(students),
            "n_test_students": len(test_students), "skipped_rows": skipped,
            "dropped_development_entries_with_exact_test_duplicates": len(dropped_entries),
            "split_note": "Deterministic person-disjoint split. Public questions remain exposed, not a fresh holdout.",
            "cases": cases}
    validate_manifest(data)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Import JorGPT CSV files to validated evaluation manifest.")
    parser.add_argument("--english", required=True, help="Path to English JorGPT CSV")
    parser.add_argument("--spanish", help="Optional path to Spanish paired CSV")
    parser.add_argument("--output", required=True, help="Path to output manifest JSON")
    parser.add_argument("--report", help="Optional path to machine-readable validation report JSON")
    args = parser.parse_args()

    en_path = Path(args.english)
    es_path = Path(args.spanish) if args.spanish else None

    data = convert(read(en_path), read(es_path) if es_path else None)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    grades = [c["label"] for c in data["cases"]]
    dev_count = sum(1 for c in data["cases"] if c["split"] == "development")
    test_count = sum(1 for c in data["cases"] if c["split"] == "test")
    en_count = sum(1 for c in data["cases"] if c["language"] == "en")
    es_count = sum(1 for c in data["cases"] if c["language"] == "es")

    report = {
        "dataset_id": "jorgpt",
        "validation_status": "passed",
        "inputs": {"english": str(en_path), "spanish": str(es_path) if es_path else None},
        "output_manifest": str(out_path),
        "total_cases": len(data["cases"]),
        "unique_students": data["n_students"],
        "test_students": data["n_test_students"],
        "skipped_rows": data["skipped_rows"],
        "dropped_test_duplicate_entries": data["dropped_development_entries_with_exact_test_duplicates"],
        "split_distribution": {"development": dev_count, "test": test_count},
        "languages": {"en": en_count, "es": es_count},
        "grade_metrics": {
            "scale": "0.0 - 10.0",
            "min": min(grades) if grades else 0.0,
            "max": max(grades) if grades else 0.0,
            "mean": sum(grades) / len(grades) if grades else 0.0,
        },
    }

    if args.report:
        rep_path = Path(args.report)
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

