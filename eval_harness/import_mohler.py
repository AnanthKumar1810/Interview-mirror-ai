"""Import the CC BY 4.0 Mohler ASAG mirror without inventing student identities.

Writes a private local evaluation manifest; it does not commit dataset rows.
Source: https://huggingface.co/datasets/nkazi/MohlerASAG
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from eval_harness.gnani_paths import validate_manifest

BASE = "https://datasets-server.huggingface.co/rows"
REVISION = "dac06732b42d01a5169f543f6d272f1476cced3e"


def fetch_page(offset: int, length: int = 100) -> dict:
    query = urlencode({"dataset": "nkazi/MohlerASAG", "config": "raw",
                       "split": "open_ended", "offset": offset, "length": length})
    for attempt in range(3):
        try:
            with urlopen(BASE + "?" + query, timeout=30) as response:
                return json.load(response)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def convert(rows: list[dict]) -> tuple[list[dict], int]:
    cases = []
    skipped = 0
    for item in rows:
        row = item["row"]
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in
                   ("id", "question", "instructor_answer", "student_answer")):
            skipped += 1
            continue
        score = row.get("score_avg")
        if not isinstance(score, (float, int)) or not 0 <= score <= 5:
            skipped += 1
            continue
        cases.append({"id": "mohler:" + row["id"], "dataset": "mohler_asag",
                      "split": "test", "person_id": "unknown_all_test",
                      "variant_group_id": row["id"], "question": row["question"].strip(),
                      "reference": row["instructor_answer"].strip(),
                      "transcript": row["student_answer"].strip(),
                      "label_kind": "numeric", "label": score, "label_max": 5,
                      "source_id": row["id"], "grader_1": row["score_grader_1"],
                      "grader_2": row["score_grader_2"]})
    return cases, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    first = fetch_page(0)
    total = first["num_rows_total"]
    rows = list(first["rows"])
    for offset in range(len(rows), total, 100):
        page = fetch_page(offset)
        if page["num_rows_total"] != total:
            raise ValueError("Source changed during import")
        rows.extend(page["rows"])
    if len(rows) != total or len({r["row_idx"] for r in rows}) != total:
        raise ValueError("Missing or duplicate source rows")
    cases, skipped = convert(rows)
    data = {"dataset_id": "mohler_asag", "source": "nkazi/MohlerASAG",
            "source_revision_observed": REVISION, "license_declared": "CC BY 4.0",
            "split_note": "All rows are test-only; the public mirror does not expose student identities.",
            "cases": cases}
    validate_manifest(data)
    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_rows": total, "imported": len(cases), "skipped": skipped,
                      "output": args.output}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

