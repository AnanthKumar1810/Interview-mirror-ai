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


def load_local_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Mohler source file not found: {path}")
    raw_content = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in Mohler input file: {exc}") from exc
    if isinstance(parsed, list):
        rows = []
        for idx, item in enumerate(parsed):
            if isinstance(item, dict) and "row" in item:
                rows.append(item)
            elif isinstance(item, dict):
                rows.append({"row_idx": idx, "row": item})
            else:
                raise ValueError(f"Unexpected item type at row {idx}")
        return rows
    elif isinstance(parsed, dict) and "rows" in parsed and isinstance(parsed["rows"], list):
        return parsed["rows"]
    elif isinstance(parsed, dict) and "cases" in parsed:
        return [{"row_idx": idx, "row": {
            "id": c.get("source_id", c["id"].removeprefix("mohler:")),
            "question": c["question"],
            "instructor_answer": c["reference"],
            "student_answer": c["transcript"],
            "score_avg": c["label"],
            "score_grader_1": c.get("grader_1", c["label"]),
            "score_grader_2": c.get("grader_2", c["label"]),
        }} for idx, c in enumerate(parsed["cases"])]
    raise ValueError("Mohler input file structure not recognized as rows array or dataset format")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Mohler ASAG dataset to validated evaluation manifest.")
    parser.add_argument("--input", help="Optional path to local Mohler ASAG JSON source file for offline import")
    parser.add_argument("--output", required=True, help="Path to output manifest JSON")
    parser.add_argument("--report", help="Optional path to machine-readable validation report JSON")
    args = parser.parse_args()

    if args.input:
        in_path = Path(args.input)
        rows = load_local_rows(in_path)
        total = len(rows)
    else:
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

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    scores = [c["label"] for c in cases]
    report = {
        "dataset_id": "mohler_asag",
        "validation_status": "passed",
        "input_mode": "local_file" if args.input else "huggingface_api",
        "input_path": str(args.input) if args.input else "https://datasets-server.huggingface.co/rows",
        "output_manifest": str(out_path),
        "source_rows": total,
        "imported_cases": len(cases),
        "skipped_rows": skipped,
        "all_test_split": True,
        "score_metrics": {
            "scale": "0.0 - 5.0",
            "min": min(scores) if scores else 0.0,
            "max": max(scores) if scores else 0.0,
            "mean": sum(scores) / len(scores) if scores else 0.0,
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

