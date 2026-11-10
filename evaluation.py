"""Auditable transcript-only coaching rubric.

IMPORTANT: Lexical evidence and claimed results are NOT a correctness oracle. A
matched technical term only shows that a candidate mentioned a relevant concept.
This is a learning aid, not an employment assessment or a speech diagnosis.
"""
from __future__ import annotations

import re
from collections import OrderedDict

DIMENSION_MAX = OrderedDict([
    ("relevance", 25),
    ("technical_coverage", 35),
    ("clarity", 20),
    ("evidence", 20),
])

# Each group is one expected concept. Terms include common Indian-English and
# code-mixed Telugu/Hindi spellings. The lists are deliberately small and are
# NOT a general semantic or factual evaluation model.
CONCEPTS = {
    "ai": [
        [("project / model", ["project", "model", "ప్రాజెక్ట్", "మోడల్", "परियोजना", "मॉडल"]),
         ("data / training", ["data", "dataset", "train", "డేటా", "శిక్షణ", "डेटा", "प्रशिक्षण"]),
         ("problem / outcome", ["problem", "classif", "predict", "accuracy", "సమస్య", "ఖచ్చిత", "समस्या", "सटीक"])],
        [("evaluation metric", ["metric", "precision", "recall", "accuracy", "qwk", "మెట్రిక్", "ఖచ్చిత", "मूल्यांकन"]),
         ("validation method", ["validat", "test", "holdout", "పరీక్ష", "परीक्षण", "जांच"]),
         ("improvement action", ["improv", "tune", "augment", "సరిచే", "మెరుగు", "सुधार"])],
        [("deployment", ["deploy", "serv", "release", "డిప్లాయ్", "విడుదల", "तैनात"]),
         ("operational constraints", ["latency", "monitor", "scale", "cost", "వేగ", "నిరీక్ష", "निगरानी"]),
         ("user / data safeguards", ["privacy", "user", "fairness", "వినియోగ", "గోప్యత", "उपयोगकर्ता", "गोपनीय"])],
    ],
    "agentic": [
        [("agent workflow", ["agent", "workflow", "orchestrat", "ఏజెంట్", "ఏజెంట", "एजेंट"]),
         ("tools", ["tool", "function call", "api", "టూల్", "సాధన", "टूल"]),
         ("action controls", ["approv", "permission", "guardrail", "restrict", "validat", "అనుమతి", "నియంత్ర", "अनुमति", "नियंत्र"])],
        [("reliability tests", ["test", "evaluat", "benchmark", "పరీక్ష", "परीक्षण", "मूल्यांकन"]),
         ("observed failure", ["fail", "error", "bug", "hallucinat", "ఫెయిల్", "లోప", "विफल", "त्रुटि"]),
         ("recovery / safeguards", ["retry", "repair", "validat", "rollback", "recover", "సరి", "పున", "सुधार"])],
        [("human approval", ["human", "approv", "review", "అనుమతి", "మానవ", "मानव", "मंजूरी"]),
         ("change evidence", ["diff", "log", "audit", "test", "డిఫ్", "లాగ", "लॉग"]),
         ("safety / rollback", ["rollback", "guardrail", "restrict", "undo", "నియంత్ర", "సురక్ష", "सुरक्षा"])],
    ],
    "software": [
        [("bug / failure", ["bug", "fail", "error", "బగ్", "లోప", "त्रुटि", "बग"]),
         ("root-cause investigation", ["trace", "debug", "reproduc", "root cause", "కారణ", "పరిశోధ", "जड़", "कारण"]),
         ("verification", ["test", "validat", "assert", "పరీక్ష", "టెస్ట్", "परीक्षण"])],
        [("load management", ["cache", "queue", "load", "scale", "క్యాష్", "లోడ్", "कैश", "लोड"]),
         ("failure control", ["timeout", "retry", "rate limit", "circuit", "రిట్రై", "टाइमआउट"]),
         ("data / observability", ["database", "monitor", "log", "డేటాబేస్", "లాగ", "डेटाबेस", "लॉग"])],
        [("trade-off", ["trade", "versus", "instead", "మధ్య", "बनाम", "समझौता"]),
         ("quality measure", ["test", "maintain", "quality", "నాణ్యత", "गुणवत्ता"]),
         ("delivery constraint", ["time", "deadline", "speed", "సమయం", "వేగ", "समय", "गति"])],
    ],
}

ACTION_TERMS = ["built", "implemented", "wrote", "used", "designed", "tested", "fixed", "changed", "created",
                "చేశ", "రూపొం", "వాడ", "ఉపయోగ", "పరీక్ష", "बनाया", "किया", "लिखा", "जाँचा"]
CHECK_TERMS = ["test", "verified", "measured", "benchmark", "validated", "compared", "evaluated",
               "పరీక్ష", "ధృవ", "కొల", "जांच", "परीक्षण", "मापा"]
REASON_TERMS = ["because", "therefore", "so that", "as a result", "since", "because of", "కాబట్టి", "ఎందుకంటే", "అందువల్ల", "क्योंकि", "इसलिए"]
SEQUENCE_TERMS = ["first", "then", "finally", "after", "next", "మొదట", "తర్వాత", "చివర", "पहले", "फिर", "अंत"]
MEASUREMENT_PATTERN = re.compile(r"(?<!\w)(?:\d+(?:\.\d+)?\s*(?:%|percent|milliseconds?|ms|seconds?|s|cases?|tests?|samples?|out of)|\d+\s*/\s*\d+|\d{2,})(?!\w)", re.IGNORECASE)


def _find(text: str, terms: list[str]) -> tuple[int, int] | None:
    lowered = text.lower()
    for term in terms:
        term = term.lower().strip()
        if not term:
            continue
        # English/Latin words should not accidentally match substrings of other words.
        pattern = re.escape(term)
        if term[0].isascii() and term[0].isalnum():
            pattern = r"(?<![a-z0-9])" + pattern
        if term[-1].isascii() and term[-1].isalnum() and not term.endswith(("train", "improv", "validat", "classif", "reproduc", "approv", "orchestrat", "evaluat", "restrict", "monitor", "maintain", "hallucinat", "releas", "serv")):
            pattern += r"(?![a-z0-9])"
        found = re.search(pattern, lowered)
        if found:
            return found.span()
    return None


def _quote(text: str, span: tuple[int, int], radius: int = 38) -> str:
    """Never generate a quote that wasn't in the candidate's submitted answer."""
    start, end = span
    return text[max(0, start - radius): min(len(text), end + radius)].strip()


def _evidence_record(dimension: str, text: str, span: tuple[int, int], observation: str) -> dict:
    return {"dimension": dimension, "quote": _quote(text, span), "observation": observation}


def evaluate_answer(transcript: str, question: dict, language: str, track: str | None = None, index: int | None = None) -> dict:
    text = transcript.strip()
    words = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    concept_defs = question.get("concepts")
    if concept_defs is None and track in CONCEPTS and isinstance(index, int) and 0 <= index < 3:
        concept_defs = CONCEPTS[track][index]
    if concept_defs is None:
        # Backward compatibility for third-party question objects.
        concept_defs = [(term, [term]) for term in question.get("keywords", []) if term.isascii()][:3]

    coverage = []
    evidences = []
    for label, variants in concept_defs:
        match = _find(text, variants)
        entry = {"concept": label, "mentioned": bool(match), "quote": _quote(text, match) if match else None}
        coverage.append(entry)
        if match:
            evidences.append(_evidence_record("technical_coverage", text, match, f"Mentioned a term related to {label}; correctness is not independently verified."))

    matches = sum(item["mentioned"] for item in coverage)
    reasoning = _find(text, REASON_TERMS)
    sequencing = _find(text, SEQUENCE_TERMS)
    actions = _find(text, ACTION_TERMS)
    checked = _find(text, CHECK_TERMS)
    measurement = MEASUREMENT_PATTERN.search(text)
    measurements_span = measurement.span() if measurement else None

    # Deterministic, deliberately modest indicators. Zero relevance/coverage for
    # unmatched concepts guards against long generic speeches receiving high grades.
    relevance = min(25, 7 + 6 * matches + (2 if len(words) >= 30 else 0)) if matches else 0
    technical_coverage = min(35, 10 * matches + (5 if reasoning and matches else 0))
    clause_count = len([x for x in re.split(r"[.!?।\n]+", text) if x.strip()])
    clarity = min(20, (6 if len(words) >= 12 else 2 if len(words) >= 3 else 0) +
                  (5 if len(words) >= 30 else 0) + (4 if sequencing or reasoning else 0) +
                  (5 if clause_count >= 2 else 0))
    support = (6 if actions else 0) + (7 if checked else 0) + (7 if measurement else 0)
    evidence_score = support if matches else min(support, 5)
    dimensions = {"relevance": relevance, "technical_coverage": technical_coverage,
                  "clarity": clarity, "evidence": evidence_score}

    if reasoning:
        evidences.append(_evidence_record("clarity", text, reasoning, "Includes a causal explanation or reason."))
    elif sequencing:
        evidences.append(_evidence_record("clarity", text, sequencing, "Includes an ordering or sequence cue."))
    if actions:
        evidences.append(_evidence_record("evidence", text, actions, "Describes an action; the outcome is not independently verified."))
    if checked:
        evidences.append(_evidence_record("evidence", text, checked, "Mentions a verification or measurement method."))
    if measurements_span:
        evidences.append(_evidence_record("evidence", text, measurements_span, "Includes a quantified statement; the number is unverified."))

    missing = [item["concept"] for item in coverage if not item["mentioned"]]
    strengths = []
    if matches:
        strengths.append(f"Mentions {matches} of {len(coverage)} expected technical areas; see the verbatim excerpts below.")
    if checked:
        strengths.append("Describes a check or validation step in the response.")
    if measurement:
        strengths.append("Includes a measurable statement (not independently verified).")
    if not strengths:
        strengths.append("An answer was supplied; its relevance needs more concrete technical detail.")

    improvements = []
    if missing:
        improvements.append("Address the missing concepts: " + ", ".join(missing[:3]) + ".")
    if not measurement:
        improvements.append("Add one verifiable outcome or measurement, if available, without inventing numbers.")
    if not checked:
        improvements.append("Explain how you tested or validated the result.")
    if len(words) < 25:
        improvements.append("Add context: describe the problem, your decision and the observed result.")
    elif not reasoning:
        improvements.append("Explain why you chose this approach and what alternative you considered.")
    if not improvements:
        improvements.append("Discuss a limitation or trade-off and explain how you would test it.")

    score = sum(dimensions.values())
    return {
        "score": score,
        "dimensions": dimensions,
        "dimension_max": dict(DIMENSION_MAX),
        "coverage": coverage,
        "missing_concepts": missing,
        "evidence_items": evidences[:8],
        "strengths": strengths[:3],
        "improvements": improvements[:4],
        "follow_up": {
            "en-IN": "What trade-off did you face, and how did you verify your chosen solution?",
            "te-IN": "మీరు ఏ నిర్ణయానికి వచ్చారు? దాని ఫలితాన్ని ఎలా ధృవీకరించారు?",
            "hi-IN": "आपने क्या समझौता किया और अपने समाधान को कैसे जाँचा?",
        }.get(language, "What trade-off did you face and how did you verify it?"),
        "method": "transparent_concept_coverage_rubric_v2",
        "factual_assessment": "not_verified",
        "disclaimer": "Indicative practice rubric from transcript signals. Term coverage is not proof of technical correctness. Measured claims are unverified. Not a hiring, pronunciation or confidence assessment.",
    }
