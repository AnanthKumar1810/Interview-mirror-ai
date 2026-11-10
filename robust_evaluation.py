"""Risk-aware interview practice scoring with conservative correctness checks.

A calibrated interview score is NOT available without human-adjudicated labels.
This module offers testable safeguards against specific adversarial behaviours.
An optional structured semantic judge can add *model-generated*, non-authoritative
signals; never describe it as human validation or a correctness oracle.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Callable

from evaluation import DIMENSION_MAX, evaluate_answer

# Targeted controls cover the actual observed synthetic failure cases. These
# patterns are intentionally specific and are not general fact verification.
PATTERNS = [
    ("absolute_perfection_claim", re.compile(r"\b(?:100\s*(?:%|percent)|perfect\s+accuracy)\b.{0,90}\b(?:never|always|impossible|no\s+mistakes)\b", re.I | re.S),
     "A perfect score does not establish guaranteed future correctness."),
    ("absolute_perfection_claim", re.compile(r"\b(?:never\s+make\s+(?:another\s+)?mistake|always\s+(?:be\s+)?correct|guaranteed\s+accuracy)\b", re.I),
     "Absolute correctness claims require extraordinary independent evidence."),
    ("known_metric_confusion", re.compile(r"\bprecision\s+(?:is|equals|=)\s*(?:tp\s*/\s*\(\s*tp\s*\+\s*fn|true positives divided by (?:true positives plus )?false negatives)", re.I),
     "The response appears to confuse precision with recall."),
    ("data_leakage_claim", re.compile(r"\b(?:train(?:ed|ing)?\s+on\s+(?:the\s+)?test\s+(?:set|data)|(?:test\s+(?:set|data))\s+(?:was|were)\s+used\s+(?:for|to)\s+train|used\s+(?:my|the)?\s*test\s+(?:set|data)\s+to\s+train)\b", re.I),
     "Training on test data can invalidate a held-out generalization assessment."),
]


def _quote(text: str, span: tuple[int, int], radius: int = 25) -> str:
    return text[max(0, span[0] - radius):min(len(text), span[1] + radius)].strip()


def _repetition(text: str) -> tuple[bool, str]:
    # Python's default \w splits Indic combining marks. Never use it to
    # estimate lexical repetition in Telugu/Hindi. Restrict this safety check
    # to repeated *Latin* technical phrases, including in code-mixed answers.
    tokens = re.findall(r"[a-z]+", text.casefold())
    if len(tokens) < 12:
        return False, ""
    ngrams = Counter(tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2))
    if any(count >= 2 for count in ngrams.values()) and len(tokens) >= 16:
        return True, "Repeated technical phrases are not evidence of conceptual understanding."
    return False, ""


def _valid_semantic_signal(signal: object, text: str) -> dict | None:
    if not isinstance(signal, dict):
        return None
    verdict = signal.get("verdict")
    excerpt = signal.get("quote")
    if verdict not in {"supported", "uncertain", "contradicted"}:
        return None
    if not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in text:
        return None
    reason = signal.get("reason", "")
    if not isinstance(reason, str):
        return None
    return {"verdict": verdict, "quote": excerpt, "reason": reason[:240]}


def evaluate_robust(
    transcript: str, question: dict, language: str,
    track: str | None = None, index: int | None = None,
    *, semantic_judge: Callable[[str, dict, str], dict] | None = None,
) -> dict:
    result = evaluate_answer(transcript, question, language, track, index)
    dims = dict(result["dimensions"])
    flags: list[dict] = []
    for code, pattern, explanation in PATTERNS:
        match = pattern.search(transcript)
        if match and not any(item["code"] == code for item in flags):
            flags.append({"code": code, "quote": _quote(transcript, match.span()),
                          "explanation": explanation})
    repeats, explanation = _repetition(transcript)
    if repeats:
        # Verbatim candidate text is evidence of repetition, not an invented quote.
        flags.append({"code": "keyword_stuffing", "quote": transcript[:120].strip(),
                      "explanation": explanation})

    # Constrain the dimensions rather than deducting a hidden number from total.
    if any(f["code"] == "keyword_stuffing" for f in flags):
        dims["technical_coverage"] = min(dims["technical_coverage"], 10)
        dims["evidence"] = min(dims["evidence"], 3)
        dims["clarity"] = min(dims["clarity"], 8)
    if any(f["code"] in {"absolute_perfection_claim", "known_metric_confusion", "data_leakage_claim"} for f in flags):
        dims["technical_coverage"] = min(dims["technical_coverage"], 10)
        dims["evidence"] = min(dims["evidence"], 3)
        dims["relevance"] = min(dims["relevance"], 15)

    semantic = None
    if semantic_judge is not None:
        try:
            semantic = _valid_semantic_signal(semantic_judge(transcript, question, language), transcript)
        except Exception:
            semantic = None   # Safe, explicit fallback; never pretend LLM ran.
        if semantic and semantic["verdict"] == "contradicted":
            flags.append({"code": "model_flagged_possible_contradiction",
                          "quote": semantic["quote"],
                          "explanation": semantic["reason"] or "LLM flagged possible contradiction; human review recommended."})
            dims["technical_coverage"] = min(dims["technical_coverage"], 10)
            dims["evidence"] = min(dims["evidence"], 3)
        elif semantic and semantic["verdict"] == "uncertain":
            flags.append({"code": "model_uncertain", "quote": semantic["quote"],
                          "explanation": semantic["reason"] or "A reviewer should inspect this claim."})

    assert all(0 <= dims[d] <= cap for d, cap in DIMENSION_MAX.items())
    result.update({
        "score": sum(dims.values()), "dimensions": dims,
        "method": "risk_aware_rubric_v3" + ("_with_optional_llm_signal" if semantic else ""),
        "factual_assessment": "model_assessed_not_verified" if semantic else "not_verified",
        "risk_flags": flags,
        "semantic_signal": semantic,
        "human_review_recommended": bool(flags) or semantic is None,
        "scoring_confidence": "unvalidated",
        "disclaimer": "Uncalibrated practice feedback. Heuristic safeguards and optional LLM assessments are not human-verified technical correctness, hiring decisions, or speech fluency scores.",
    })
    if flags:
        result["improvements"] = ["Review these potentially incorrect or unsupported claims with a qualified human or authoritative source."] + result["improvements"][:3]
        result["evidence_items"] = (result["evidence_items"] + [
            {"dimension": "technical_coverage", "quote": item["quote"], "observation": item["explanation"]}
            for item in flags
        ])[:12]
    return result


def evaluate_for_app(transcript: str, question: dict, language: str,
                     track: str | None = None, index: int | None = None) -> dict:
    """Default safe rubric; LLM review is explicit via IM_SEMANTIC_JUDGE=ollama."""
    judge = None
    if os.getenv("IM_SEMANTIC_JUDGE", "off").strip().lower() == "ollama":
        from semantic_judge import judge_with_ollama
        judge = judge_with_ollama
    return evaluate_robust(transcript, question, language, track, index, semantic_judge=judge)
