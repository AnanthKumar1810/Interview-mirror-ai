"""Verification of Phase 7: Adaptive difficulty tiers and Socratic question bank."""
import pytest
from adaptive import (
    DIFFICULTY_LEVELS,
    SOCRATIC_BANK,
    select_followup,
)


@pytest.mark.parametrize("track", ["agentic", "ai", "software"])
@pytest.mark.parametrize("level", ["fundamentals", "applied", "architecture"])
@pytest.mark.parametrize("focus", ["technical", "evidence", "clarity", "tradeoff"])
def test_socratic_bank_structure_and_localization(track, level, focus):
    entry = SOCRATIC_BANK[track][level][focus]
    assert "en-IN" in entry
    assert "te-IN" in entry
    assert "hi-IN" in entry
    assert "concepts" in entry
    assert len(entry["concepts"]) == 3
    for label, variants in entry["concepts"]:
        assert isinstance(label, str) and label
        assert isinstance(variants, list) and len(variants) >= 2


@pytest.mark.parametrize("track", ["agentic", "ai", "software"])
def test_dynamic_tier_selection_from_scores(track):
    # Low score -> fundamentals
    low_feedback = {
        "score": 25,
        "dimensions": {"technical_coverage": 10, "evidence": 5, "clarity": 5, "relevance": 5}
    }
    item_low, _, focus_low = select_followup(track, "en-IN", low_feedback)
    assert item_low["level"] == "fundamentals"
    assert focus_low == "technical"
    assert item_low["question_type"] == "socratic"

    # Medium score -> applied
    mid_feedback = {
        "score": 55,
        "dimensions": {"technical_coverage": 25, "evidence": 8, "clarity": 12, "relevance": 10}
    }
    item_mid, _, focus_mid = select_followup(track, "en-IN", mid_feedback)
    assert item_mid["level"] == "applied"
    assert focus_mid == "evidence"

    # High score -> architecture
    high_feedback = {
        "score": 85,
        "dimensions": {"technical_coverage": 30, "evidence": 18, "clarity": 18, "relevance": 19}
    }
    item_high, _, focus_high = select_followup(track, "en-IN", high_feedback)
    assert item_high["level"] == "architecture"
    assert focus_high == "tradeoff"


def test_explicit_level_override():
    feedback = {
        "score": 20,
        "dimensions": {"technical_coverage": 5, "evidence": 5, "clarity": 5, "relevance": 5}
    }
    # Force architecture tier despite low score
    item, reason, focus = select_followup("agentic", "te-IN", feedback, level="architecture")
    assert item["level"] == "architecture"
    assert focus == "technical"
    assert "టూల్" in item["te-IN"] or "ప్రొడక్షన్" in item["te-IN"] or "నియంత్ర" in item["te-IN"]


def test_dynamic_conversational_followup_generation():
    from adaptive import generate_dynamic_followup

    # 1. Self introduction with name and college
    ans1 = "My name is Ananth Kumar, studying at MJ College of Engineering, passionate about machine learning and Python."
    next_q = {"en-IN": "Tell me about a binary classifier you trained."}
    spoken1, ack1 = generate_dynamic_followup(ans1, {}, next_q, language="en-IN", question_index=0)
    assert "Ananth Kumar" in ack1
    assert "MJ College of Engineering" in ack1
    assert "Tell me about a binary classifier" in spoken1

    # 2. Precision vs recall explanation
    ans2 = "Well, precision it is called how well the model has done the things, and recall means how about the thing it is recalling the things."
    next_q2 = {"en-IN": "In a fraud detection system, which would you prioritize, and why?"}
    spoken2, ack2 = generate_dynamic_followup(ans2, {}, next_q2, language="en-IN", question_index=1)
    assert "precision as correctness" in ack2.lower() or "predicted positives" in ack2.lower()
    assert "fraud detection" in spoken2

    # 3. Precision prioritization in fraud detection
    ans3 = "I would prioritize precision, as it is important that it may be best for the things like getting exactly whether any fraud has occurred or not."
    next_q3 = {"en-IN": "What's one concrete threshold tuning approach you'd use to trade off false positives vs. false negatives?"}
    spoken3, ack3 = generate_dynamic_followup(ans3, {}, next_q3, language="en-IN", question_index=2)
    assert "maximizing correctness" in ack3.lower() or "precision" in ack3.lower()
    assert "threshold tuning" in spoken3
