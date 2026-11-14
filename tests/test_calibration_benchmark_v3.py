"""Tests for Calibration Benchmark v3.0 (Plan X+ V3).

Verifies scoring calibration across:
- Strong answers
- Irrelevant / empty answers
- Known misconceptions (asyncio parallel CPU, docker full VM, 100% accuracy, metric confusion, data leakage)
- Adversarial keyword stuffing
- Code-mixed Telugu-English and Hindi-English answers
- Conversational dialogue intents (clarification, repeat, uncertainty, skip)
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from coach import QUESTION_BANK
from robust_evaluation import evaluate_robust
from conversational_engine import DialoguePolicy


def test_calibration_benchmark_cases():
    data_path = Path(__file__).parent.parent / "eval_harness" / "datasets" / "calibration_benchmark_v3.json"
    with open(data_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    cases = manifest["cases"]
    assert len(cases) >= 20

    for case in cases:
        ans = case["answer"]
        track = case["track"]
        lang = case["language"]
        q_idx = case["question_index"]
        category = case["category"]

        if category.startswith("dialogue_"):
            # Verify intent classification
            expected_intent = case["expected_intent"]
            classified = DialoguePolicy.classify_intent(ans)
            assert classified == expected_intent, f"Case {case['id']}: expected {expected_intent}, got {classified}"
        else:
            q_spec = QUESTION_BANK[track][q_idx]
            result = evaluate_robust(ans, q_spec, lang, track, q_idx)
            score = result["score"]
            risks = [r["code"] for r in result.get("risks", []) if isinstance(r, dict)]

            if category == "strong" or category == "code_mixed_strong":
                assert score >= 60, f"Case {case['id']}: expected score >= 60, got {score}"
                assert len(risks) == 0, f"Case {case['id']}: unexpected risks {risks}"
            elif category == "irrelevant":
                assert score <= 15, f"Case {case['id']}: expected score <= 15, got {score}"
            elif category == "misconception":
                assert score < 50, f"Case {case['id']}: expected constrained score < 50, got {score}"
                for exp_risk in case.get("expected_risks", []):
                    assert exp_risk in risks, f"Case {case['id']}: expected risk {exp_risk}, got {risks}"
            elif category == "adversarial":
                assert score < 50, f"Case {case['id']}: adversarial stuffing score must be capped < 50, got {score}"
                assert any(r in ("keyword_stuffing", "disconnected_keyword_list") for r in risks)
