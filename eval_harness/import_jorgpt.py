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
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--english", required=True)
    parser.add_argument("--spanish")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = convert(read(Path(args.english)), read(Path(args.spanish)) if args.spanish else None)
    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(data["cases"]), "students": data["n_students"],
                      "test_students": data["n_test_students"], "skipped": data["skipped_rows"],
                      "output": args.output}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

