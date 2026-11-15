"""Private human-annotation workflow for InterviewMirror's consented gold set.

This CLI never creates reference labels. Reviewers fill separate blinded JSON
forms; only two independent reviews plus required adjudication can be sealed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from eval_harness.gold_evaluation import (
    AdjudicationRecord,
    ConsentRecord,
    GoldCase,
    GoldEvaluationSet,
    RUBRIC_DIMENSIONS,
    ReviewerRating,
    partition_cases_grouped,
)


def _construct(cls, value: dict | None):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {cls.__name__}.")
    allowed = cls.__dataclass_fields__.keys()
    return cls(**{key: item for key, item in value.items() if key in allowed})


def load_dataset(path: Path) -> GoldEvaluationSet:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read gold dataset JSON: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("cases", []), list):
        raise ValueError("Dataset must be a JSON object with a cases array.")
    cases = []
    for index, item in enumerate(raw.get("cases", [])):
        if not isinstance(item, dict):
            raise ValueError(f"Case {index} must be an object.")
        case_data = dict(item)
        case_data["consent"] = _construct(ConsentRecord, case_data.get("consent"))
        if case_data["consent"] is None:
            raise ValueError(f"Case {index} is missing its consent record.")
        case_data["reviewers"] = [_construct(ReviewerRating, row) for row in case_data.get("reviewers", [])]
        case_data["adjudication"] = _construct(AdjudicationRecord, case_data.get("adjudication"))
        allowed = GoldCase.__dataclass_fields__.keys()
        cases.append(GoldCase(**{key: value for key, value in case_data.items() if key in allowed}))
    allowed = GoldEvaluationSet.__dataclass_fields__.keys()
    dataset_data = {key: value for key, value in raw.items() if key in allowed and key != "cases"}
    return GoldEvaluationSet(**dataset_data, cases=cases)


def write_dataset(path: Path, dataset: GoldEvaluationSet) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(dataset), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def holdout_digest(dataset: GoldEvaluationSet) -> str:
    rows = [asdict(case) for case in sorted(dataset.cases, key=lambda item: item.case_id)
            if case.split == "locked_test_holdout"]
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_dataset(dataset: GoldEvaluationSet) -> dict[str, Any]:
    if dataset.status not in {"incomplete", "adjudicated_ready"}:
        raise ValueError("Dataset status must be incomplete or adjudicated_ready.")
    if not dataset.dataset_id.strip() or not dataset.version.strip():
        raise ValueError("Dataset ID and version are required.")
    ids = [case.case_id for case in dataset.cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case_id values are not allowed.")
    for case in dataset.cases:
        if case.pii_redacted is not True:
            raise ValueError(f"Case {case.case_id}: confirm PII redaction before gold-set processing.")
        case.validate(require_reviews=dataset.status == "adjudicated_ready",
                      require_adjudication=dataset.status == "adjudicated_ready")
    leakage = dataset.validate_leakage()
    locked = [case for case in dataset.cases if case.split == "locked_test_holdout"]
    if dataset.status == "adjudicated_ready":
        if not locked:
            raise ValueError("A ready dataset requires at least one locked holdout case.")
        if not dataset.holdout_sha256 or dataset.holdout_sha256 != holdout_digest(dataset):
            raise ValueError("Locked holdout digest is missing or has changed; do not edit a sealed holdout.")
    elif dataset.holdout_sha256:
        raise ValueError("An incomplete dataset cannot claim a sealed holdout digest.")
    return {
        **leakage,
        "status": dataset.status,
        "gold_examples_count": len(locked) if dataset.status == "adjudicated_ready" else 0,
        "pending_review_cases": sum(1 for case in dataset.cases if len(case.reviewers) < 2),
        "holdout_sha256": dataset.holdout_sha256,
    }


def case_fingerprint(case: GoldCase) -> str:
    values = [case.question_text, case.reference_answer, case.candidate_answer,
              case.domain, case.language, str(case.code_mixed)]
    payload = "\0".join(values).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def export_review_forms(dataset: GoldEvaluationSet, reviewer_ids: list[str], output: Path) -> int:
    if dataset.status != "incomplete":
        raise ValueError("Review forms may only be exported from an incomplete dataset.")
    if len(reviewer_ids) < 2 or len(set(reviewer_ids)) != len(reviewer_ids):
        raise ValueError("Supply at least two distinct reviewer IDs.")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", reviewer) for reviewer in reviewer_ids):
        raise ValueError("Reviewer IDs may contain only letters, numbers, dot, underscore, and dash.")
    for case in dataset.cases:
        if case.pii_redacted is not True:
            raise ValueError(f"Case {case.case_id}: PII must be redacted before exporting reviewer forms.")
        case.validate(require_reviews=False, require_adjudication=False)
    count = 0
    for reviewer in reviewer_ids:
        rows = []
        for case in dataset.cases:
            if reviewer in {rating.reviewer_id for rating in case.reviewers}:
                continue
            rows.append({
                "case_id": case.case_id,
                "case_fingerprint": case_fingerprint(case),
                "question_text": case.question_text,
                "reference_answer": case.reference_answer,
                "candidate_answer": case.candidate_answer,
                "domain": case.domain,
                "language": case.language,
                "code_mixed": case.code_mixed,
                "rubric_dimensions": {
                    key: {"min": value["min"], "max": value["max"]}
                    for key, value in RUBRIC_DIMENSIONS.items()
                },
                "rating": None,
            })
        form = {"form_version": 1, "dataset_id": dataset.dataset_id,
                "reviewer_id": reviewer, "cases": rows}
        reviewer_dir = output / reviewer
        reviewer_dir.mkdir(parents=True, exist_ok=True)
        (reviewer_dir / "review.json").write_text(
            json.dumps(form, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        count += len(rows)
    return count


def import_review(dataset: GoldEvaluationSet, form_path: Path) -> int:
    try:
        form = json.loads(form_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read reviewer form: {exc}") from exc
    if not isinstance(form, dict) or not isinstance(form.get("cases"), list):
        raise ValueError("Reviewer form must contain a cases array.")
    reviewer_id = form.get("reviewer_id")
    if form.get("dataset_id") != dataset.dataset_id or not isinstance(reviewer_id, str):
        raise ValueError("Reviewer form does not match this dataset.")
    by_id = {case.case_id: case for case in dataset.cases}
    imported = 0
    for row in form.get("cases", []):
        case = by_id.get(row.get("case_id"))
        if case is None:
            raise ValueError(f"Unknown case in reviewer form: {row.get('case_id')}")
        if row.get("case_fingerprint") != case_fingerprint(case):
            raise ValueError(f"Case content changed after form export: {case.case_id}")
        if reviewer_id in {rating.reviewer_id for rating in case.reviewers}:
            raise ValueError(f"Reviewer {reviewer_id} already rated {case.case_id}.")
        rating_data = row.get("rating")
        if not isinstance(rating_data, dict):
            raise ValueError(f"Case {case.case_id} is missing the reviewer's rating.")
        rating = ReviewerRating(reviewer_id=reviewer_id, **rating_data)
        rating.validate(case.candidate_answer)
        case.reviewers.append(rating)
        imported += 1
    return imported


def export_adjudication_form(dataset: GoldEvaluationSet, case_id: str,
                             adjudicator_id: str, output: Path) -> None:
    if dataset.status != "incomplete":
        raise ValueError("Adjudication forms may only be exported from an incomplete dataset.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", adjudicator_id):
        raise ValueError("Adjudicator ID has invalid characters.")
    case = next((item for item in dataset.cases if item.case_id == case_id), None)
    if case is None or len(case.reviewers) < 2:
        raise ValueError("A case with two independent reviews is required before adjudication.")
    if adjudicator_id in {rating.reviewer_id for rating in case.reviewers}:
        raise ValueError("Adjudicator must be independent from both reviewers.")
    if case.pii_redacted is not True:
        raise ValueError("PII must be redacted before exporting the adjudication form.")
    form = {
        "form_version": 1,
        "dataset_id": dataset.dataset_id,
        "case_id": case.case_id,
        "case_fingerprint": case_fingerprint(case),
        "adjudicator_id": adjudicator_id,
        "question_text": case.question_text,
        "reference_answer": case.reference_answer,
        "candidate_answer": case.candidate_answer,
        "reviewer_ratings": [asdict(rating) for rating in case.reviewers],
        "resolved_adjudication": None,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(form, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def partition_file(input_path: Path, output_path: Path, test_ratio: float,
                   calibration_ratio: float) -> dict[str, int]:
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read split input JSON: {exc}") from exc
    entries = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or not entries:
        raise ValueError("Split input must be a nonempty JSON array or object with a cases array.")
    if any("split" in entry for entry in entries if isinstance(entry, dict)):
        raise ValueError("Input already contains split values; use a fresh, unsplit intake file.")
    partitioned = partition_cases_grouped(entries, test_ratio, calibration_ratio)
    counts = {name: sum(item["split"] == name for item in partitioned)
              for name in ("locked_test_holdout", "calibration", "development")}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"status": "incomplete", "cases": partitioned},
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return counts


def export_gnani_holdout_manifest(dataset: GoldEvaluationSet, output_path: Path) -> int:
    """Export only sealed, human-reviewed locked-test cases for A/B/C scoring."""
    validate_dataset(dataset)
    if dataset.status != "adjudicated_ready":
        raise ValueError("Only a sealed human-reviewed dataset can export a final holdout manifest.")
    cases = []
    for case in dataset.cases:
        if case.split != "locked_test_holdout":
            continue
        score = (case.adjudication.resolved_score if case.adjudication
                 else sum(review.total_score for review in case.reviewers) / len(case.reviewers))
        verdict = (case.adjudication.resolved_verdict if case.adjudication
                   else case.reviewers[0].verdict)
        cases.append({
            "id": case.case_id,
            "dataset": "fresh_mixed_holdout",
            "split": "test",
            "person_id": case.participant_id,
            "variant_group_id": case.question_family_id,
            "question": case.question_text,
            "reference": case.reference_answer,
            "transcript": case.candidate_answer,
            "label_kind": "numeric",
            "label": score,
            "label_max": 100,
            "label_namespace": "interviewmirror_0_100",
            "human_verdict": verdict,
            "reviewer_ids": [review.reviewer_id for review in case.reviewers],
            "consent_recorded": case.consent.consented,
            "language": case.language,
            "code_mixed": case.code_mixed,
            "reference_method": "adjudicated" if case.adjudication else "mean_of_independent_reviews",
        })
    if not cases:
        raise ValueError("Sealed dataset has no locked holdout cases.")
    manifest = {"dataset_id": "interviewmirror_human_mixed_holdout",
                "dataset_version": dataset.version,
                "label_provenance": "consented independent human reviews; see reference_method per case",
                "cases": cases}
    # Reuse the exact A/B/C pipeline validator before persisting sensitive data.
    from eval_harness.gnani_paths import validate_manifest
    validate_manifest(manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage InterviewMirror's private, human-reviewed gold set.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "validate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--dataset", type=Path, required=True)
    forms = sub.add_parser("export-review-forms")
    forms.add_argument("--dataset", type=Path, required=True)
    forms.add_argument("--output-dir", type=Path, required=True)
    forms.add_argument("--reviewers", nargs="+", required=True)
    adjudication_form = sub.add_parser("export-adjudication-form")
    adjudication_form.add_argument("--dataset", type=Path, required=True)
    adjudication_form.add_argument("--case-id", required=True)
    adjudication_form.add_argument("--adjudicator-id", required=True)
    adjudication_form.add_argument("--output", type=Path, required=True)
    partition = sub.add_parser("partition")
    partition.add_argument("--input", type=Path, required=True)
    partition.add_argument("--output", type=Path, required=True)
    partition.add_argument("--test-ratio", type=float, default=0.2)
    partition.add_argument("--calibration-ratio", type=float, default=0.1)
    export_manifest = sub.add_parser("export-gnani-holdout-manifest")
    export_manifest.add_argument("--dataset", type=Path, required=True)
    export_manifest.add_argument("--output", type=Path, required=True)
    imp = sub.add_parser("import-review")
    imp.add_argument("--dataset", type=Path, required=True)
    imp.add_argument("--form", type=Path, required=True)
    adjudicate = sub.add_parser("import-adjudication")
    adjudicate.add_argument("--dataset", type=Path, required=True)
    adjudicate.add_argument("--form", type=Path, required=True)
    seal = sub.add_parser("seal")
    seal.add_argument("--dataset", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "partition":
            counts = partition_file(args.input, args.output, args.test_ratio, args.calibration_ratio)
            print(json.dumps({"status": "partitioned_without_leakage", "counts": counts,
                              "output": str(args.output)}, ensure_ascii=False, indent=2))
            return 0
        dataset = load_dataset(args.dataset)
        if args.command == "export-gnani-holdout-manifest":
            count = export_gnani_holdout_manifest(dataset, args.output)
            print(json.dumps({"status": "private_final_holdout_manifest_exported",
                              "cases": count, "output": str(args.output)}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "status":
            print(json.dumps(dataset.summary(), ensure_ascii=False, indent=2))
        elif args.command == "validate":
            print(json.dumps(validate_dataset(dataset), ensure_ascii=False, indent=2))
        elif args.command == "export-review-forms":
            count = export_review_forms(dataset, args.reviewers, args.output_dir)
            print(json.dumps({"status": "forms_exported", "reviewer_count": len(args.reviewers),
                              "review_forms": count, "output_dir": str(args.output_dir)}))
        elif args.command == "export-adjudication-form":
            export_adjudication_form(dataset, args.case_id, args.adjudicator_id, args.output)
            print(json.dumps({"status": "adjudication_form_exported", "output": str(args.output)}))
        elif args.command == "import-review":
            count = import_review(dataset, args.form)
            validate_dataset(dataset)
            write_dataset(args.dataset, dataset)
            print(json.dumps({"status": "reviews_imported", "ratings_imported": count}))
        elif args.command == "import-adjudication":
            try:
                form = json.loads(args.form.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Cannot read adjudication form: {exc}") from exc
            if not isinstance(form, dict) or form.get("dataset_id") != dataset.dataset_id:
                raise ValueError("Adjudication form does not match this dataset.")
            case = next((item for item in dataset.cases if item.case_id == form.get("case_id")), None)
            if case is None:
                raise ValueError("Adjudication form references an unknown case.")
            if form.get("case_fingerprint") != case_fingerprint(case):
                raise ValueError("Case content changed after the adjudication form was prepared.")
            resolved = form.get("resolved_adjudication", form.get("adjudication"))
            if not isinstance(resolved, dict):
                raise ValueError("Adjudication form is missing the resolved rating.")
            resolved = dict(resolved)
            resolved.setdefault("adjudicator_id", form.get("adjudicator_id"))
            case.adjudication = AdjudicationRecord(**resolved)
            case.adjudication.validate()
            validate_dataset(dataset)
            write_dataset(args.dataset, dataset)
            print(json.dumps({"status": "adjudication_imported", "case_id": case.case_id}))
        elif args.command == "seal":
            if dataset.status != "incomplete":
                raise ValueError("Dataset is already sealed; create a new version before changing it.")
            validate_dataset(dataset)
            dataset.holdout_sha256 = holdout_digest(dataset)
            dataset.status = "adjudicated_ready"
            result = validate_dataset(dataset)
            write_dataset(args.dataset, dataset)
            print(json.dumps({"status": "sealed", **result}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"gold workflow error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
