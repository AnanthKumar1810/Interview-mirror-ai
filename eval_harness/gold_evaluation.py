"""Gold Evaluation Set Schema, Leakage-Resistant Partitioning & Annotation Protocol.

Complies with Gnani.ai Great Indian AI Internship requirements:
- Strictly no fabricated human labels: marks dataset incomplete with 0 gold examples
  until consented, independently adjudicated human evaluations are collected.
- At least 2 independent qualified reviewers per response, plus adjudication on disagreement.
- Person-grouped and question-family grouped splits preventing leakage across holdout and dev/calibration.
- Comprehensive provenance, consent tracking, code-mixing metadata, and data retention/deletion rules.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

VerdictType = Literal["correct", "partial", "incorrect", "uncertain"]
SplitType = Literal["locked_test_holdout", "calibration", "development"]

RUBRIC_DIMENSIONS = {
    "concept_coverage": {"min": 0, "max": 35, "description": "Technical domain concept coverage and factual accuracy"},
    "relevance_completeness": {"min": 0, "max": 25, "description": "Direct responsiveness to prompt and requirement coverage"},
    "clarity_coherence": {"min": 0, "max": 20, "description": "Structured explanation, articulation and terminological precision"},
    "evidence_tradeoffs": {"min": 0, "max": 20, "description": "Specific project examples, quantifiable metrics and trade-off analysis"},
}


@dataclass
class ReviewerRating:
    reviewer_id: str
    timestamp_utc: str
    dimensions: dict[str, float]
    total_score: float
    verdict: VerdictType
    evidence_quotes: list[str]
    rationale: str

    def validate(self, candidate_answer: str) -> None:
        if not isinstance(self.reviewer_id, str) or not self.reviewer_id.strip():
            raise ValueError("Reviewer ID must not be empty.")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("Reviewer rationale is required.")
        if not isinstance(self.evidence_quotes, list) or not all(isinstance(q, str) for q in self.evidence_quotes):
            raise ValueError("Evidence quotes must be a list of strings.")
        _validate_timestamp(self.timestamp_utc, "Reviewer timestamp")
        if not isinstance(self.dimensions, dict) or set(self.dimensions) != set(RUBRIC_DIMENSIONS):
            raise ValueError("Reviewer rating must contain exactly the configured rubric dimensions.")
        for dim, bounds in RUBRIC_DIMENSIONS.items():
            val = self.dimensions[dim]
            if (isinstance(val, bool) or not isinstance(val, (int, float))
                    or not math.isfinite(val) or not (bounds["min"] <= val <= bounds["max"])):
                raise ValueError(f"Dimension {dim} value {val} out of bounds [{bounds['min']}, {bounds['max']}]")
        expected_total = sum(self.dimensions[d] for d in RUBRIC_DIMENSIONS)
        if (isinstance(self.total_score, bool) or not isinstance(self.total_score, (int, float))
                or not math.isfinite(self.total_score) or abs(self.total_score - expected_total) > 0.01):
            raise ValueError(f"Total score {self.total_score} does not match dimension sum {expected_total}")
        if self.verdict not in ("correct", "partial", "incorrect", "uncertain"):
            raise ValueError(f"Invalid verdict: {self.verdict}")
        # Verify evidence quotes exist verbatim in candidate answer
        clean_answer = " ".join(candidate_answer.split())
        for q in self.evidence_quotes:
            clean_q = " ".join(q.split())
            if clean_q and clean_q not in clean_answer:
                raise ValueError(f"Evidence quote '{q}' not found verbatim in candidate answer.")


def _validate_timestamp(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone.")


@dataclass
class AdjudicationRecord:
    adjudicator_id: str
    timestamp_utc: str
    resolved_dimensions: dict[str, float]
    resolved_score: float
    resolved_verdict: VerdictType
    resolution_rationale: str

    def validate(self) -> None:
        if not self.adjudicator_id.strip() or not self.resolution_rationale.strip():
            raise ValueError("Adjudicator ID and resolution rationale are required.")
        _validate_timestamp(self.timestamp_utc, "Adjudication timestamp")
        if set(self.resolved_dimensions) != set(RUBRIC_DIMENSIONS):
            raise ValueError("Adjudication must contain exactly the configured rubric dimensions.")
        for dim, bounds in RUBRIC_DIMENSIONS.items():
            value = self.resolved_dimensions[dim]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not bounds["min"] <= value <= bounds["max"]):
                raise ValueError(f"Adjudicated dimension {dim} is out of bounds.")
        expected_total = sum(self.resolved_dimensions.values())
        if (isinstance(self.resolved_score, bool) or not isinstance(self.resolved_score, (int, float))
                or not math.isfinite(self.resolved_score) or abs(self.resolved_score - expected_total) > 0.01):
            raise ValueError("Adjudicated score must equal the sum of the resolved dimensions.")
        if self.resolved_verdict not in ("correct", "partial", "incorrect", "uncertain"):
            raise ValueError("Invalid adjudicated verdict.")


@dataclass
class ConsentRecord:
    consented: bool
    consent_form_version: str
    timestamp_utc: str
    purpose: str = "interview_evaluation_research"
    retention_days: int = 365
    deletion_requested: bool = False

    def validate(self) -> None:
        if self.consented is not True or self.deletion_requested:
            raise ValueError("Active, explicit consent is required for gold-set use.")
        if not self.consent_form_version.strip():
            raise ValueError("Consent form version is required.")
        _validate_timestamp(self.timestamp_utc, "Consent timestamp")
        if type(self.retention_days) is not int or self.retention_days <= 0:
            raise ValueError("Consent retention_days must be a positive integer.")


@dataclass
class GoldCase:
    case_id: str
    participant_id: str
    question_family_id: str
    question_text: str
    reference_answer: str
    candidate_answer: str
    domain: str
    language: str
    split: SplitType
    consent: ConsentRecord
    reviewers: list[ReviewerRating] = field(default_factory=list)
    adjudication: AdjudicationRecord | None = None
    audio_hash: str | None = None
    code_mixed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    pii_redacted: bool = False

    def validate(self, *, require_reviews: bool = True, require_adjudication: bool = True) -> None:
        if not all(isinstance(value, str) and value.strip() for value in (
                self.case_id, self.participant_id, self.question_family_id,
                self.question_text, self.reference_answer, self.candidate_answer,
                self.domain, self.language)):
            raise ValueError(f"Case {self.case_id}: participant_id and question_family_id are required.")
        self.consent.validate()
        if self.split not in ("locked_test_holdout", "calibration", "development"):
            raise ValueError(f"Case {self.case_id}: invalid split {self.split}")
        if self.metadata.get("synthetic") is True:
            raise ValueError(f"Case {self.case_id}: synthetic data cannot enter the gold evaluation set.")
        if require_reviews and len(self.reviewers) < 2:
            raise ValueError(f"Case {self.case_id}: Requires at least 2 independent human reviewers, got {len(self.reviewers)}.")
        reviewer_ids = [r.reviewer_id.strip() for r in self.reviewers]
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError(f"Case {self.case_id}: Reviewers must have distinct identities.")
        for r in self.reviewers:
            r.validate(self.candidate_answer)

        if len(self.reviewers) >= 2:
            score_diff = max(r.total_score for r in self.reviewers) - min(r.total_score for r in self.reviewers)
            verdict_diff = len({r.verdict for r in self.reviewers}) > 1
        else:
            score_diff, verdict_diff = 0, False
        if (score_diff > 15.0 or verdict_diff) and self.adjudication is None and require_adjudication:
            raise ValueError(
                f"Case {self.case_id}: Significant reviewer disagreement (score delta={score_diff}, "
                f"verdicts={[r.verdict for r in self.reviewers]}) requires formal adjudication."
            )
        if self.adjudication is not None:
            self.adjudication.validate()
            if self.adjudication.adjudicator_id.strip() in reviewer_ids:
                raise ValueError(f"Case {self.case_id}: adjudicator must be independent from the reviewers.")


@dataclass
class GoldEvaluationSet:
    dataset_id: str = "interviewmirror-gold-holdout-v1"
    version: str = "1.0.0"
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: Literal["incomplete", "adjudicated_ready"] = "incomplete"
    annotation_guide_version: str = "2026.11"
    cases: list[GoldCase] = field(default_factory=list)
    licensing: str = "Proprietary - Research & Evaluation Use Only"
    holdout_sha256: str | None = None

    def validate_leakage(self) -> dict[str, Any]:
        """Verify strict person and question-family disjointness across splits."""
        person_splits = defaultdict(set)
        family_splits = defaultdict(set)
        exact_text_splits = defaultdict(set)

        for case in self.cases:
            person_splits[case.participant_id].add(case.split)
            family_splits[case.question_family_id].add(case.split)
            norm_text = " ".join(case.candidate_answer.casefold().split())
            exact_text_splits[norm_text].add(case.split)

        leaked_persons = {p: s for p, s in person_splits.items() if len(s) > 1}
        leaked_families = {f: s for f, s in family_splits.items() if len(s) > 1}
        leaked_texts = {t: s for t, s in exact_text_splits.items() if len(s) > 1}

        if leaked_persons:
            raise ValueError(f"Participant leakage across splits: {leaked_persons}")
        if leaked_families:
            raise ValueError(f"Question-family leakage across splits: {leaked_families}")
        if leaked_texts:
            raise ValueError(f"Duplicate candidate answer text leakage across splits: {len(leaked_texts)} instances")

        return {
            "total_cases": len(self.cases),
            "unique_participants": len(person_splits),
            "unique_question_families": len(family_splits),
            "splits": {
                split: sum(1 for c in self.cases if c.split == split)
                for split in ("locked_test_holdout", "calibration", "development")
            },
            "leakage_audit": "PASSED - zero participant or family overlap",
        }

    def summary(self) -> dict[str, Any]:
        has_gold = len(self.cases) > 0 and self.status == "adjudicated_ready"
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "status": self.status,
            "gold_examples_count": sum(1 for c in self.cases if c.split == "locked_test_holdout") if has_gold else 0,
            "pending_review_cases": sum(1 for c in self.cases if len(c.reviewers) < 2),
            "locked_holdout_cases": sum(1 for c in self.cases if c.split == "locked_test_holdout"),
            "holdout_sha256": self.holdout_sha256,
            "provenance_note": (
                "No synthetic data permitted in gold set. Zero genuine human-adjudicated examples "
                "are presently available; data collection protocol is established."
                if not has_gold else "Fully adjudicated human holdout dataset."
            ),
            "rubric_dimensions": list(RUBRIC_DIMENSIONS.keys()),
            "supported_languages": ["en-IN", "te-IN", "hi-IN", "te-en-codemix", "hi-en-codemix"],
        }


def partition_cases_grouped(
    raw_entries: list[dict],
    test_ratio: float = 0.2,
    calibration_ratio: float = 0.1,
    seed_key: str = "interviewmirror_leakage_safe_salt_2026",
) -> list[dict]:
    """Deterministically assign person- and family-grouped splits without leakage."""
    if not (0 < test_ratio < 1) or calibration_ratio < 0 or test_ratio + calibration_ratio >= 1:
        raise ValueError("Require 0 < test_ratio < 1, calibration_ratio >= 0, and their sum < 1.")
    seen_ids = set()
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict) or not all(
                isinstance(entry.get(key), str) and entry[key].strip()
                for key in ("participant_id", "question_family_id")):
            raise ValueError(f"Entry {index} needs participant_id and question_family_id.")
        case_id = entry.get("case_id", entry.get("id"))
        if case_id is not None:
            if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
                raise ValueError(f"Entry {index} has an empty or duplicate case ID.")
            seen_ids.add(case_id)
    # Group entries into disjoint components by participant and question family
    adjacency = defaultdict(set)
    for entry in raw_entries:
        p_node = f"P:{entry['participant_id']}"
        f_node = f"F:{entry['question_family_id']}"
        adjacency[p_node].add(f_node)
        adjacency[f_node].add(p_node)

    visited = set()
    components: list[list[str]] = []
    for node in sorted(adjacency.keys()):
        if node in visited:
            continue
        comp = []
        stack = [node]
        visited.add(node)
        while stack:
            curr = stack.pop()
            comp.append(curr)
            for neighbor in adjacency[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(comp))

    # Sort components deterministically by hash of their combined IDs
    def comp_hash(comp: list[str]) -> str:
        h = hashlib.sha256(seed_key.encode("utf-8"))
        for item in comp:
            h.update(item.encode("utf-8"))
        return h.hexdigest()

    components.sort(key=comp_hash)

    # Assign components to splits
    total_entries = len(raw_entries)
    test_budget = max(1, round(total_entries * test_ratio)) if total_entries > 0 else 0
    cal_budget = (max(1, round(total_entries * calibration_ratio))
                  if total_entries > 0 and calibration_ratio > 0 else 0)

    comp_to_split: dict[str, SplitType] = {}
    test_allocated = 0
    cal_allocated = 0

    entry_counts = defaultdict(int)
    for entry in raw_entries:
        entry_counts[f"P:{entry['participant_id']}"] += 1

    for comp in components:
        comp_size = sum(entry_counts[n] for n in comp if n.startswith("P:"))
        if test_allocated + comp_size <= test_budget or test_allocated == 0:
            target_split = "locked_test_holdout"
            test_allocated += comp_size
        elif cal_allocated + comp_size <= cal_budget:
            target_split = "calibration"
            cal_allocated += comp_size
        else:
            target_split = "development"
        for node in comp:
            comp_to_split[node] = target_split

    result = []
    for entry in raw_entries:
        assigned = comp_to_split[f"P:{entry['participant_id']}"]
        res = dict(entry)
        res["split"] = assigned
        result.append(res)

    return result
