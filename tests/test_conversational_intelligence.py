"""Tests for Advanced Conversational Intelligence (Plan X+ V3).

Verifies:
1. DialoguePolicy intent classification across EN, TE, HI.
2. Clarification, repeat, uncertainty, and skip handling without unfair scoring penalties.
3. CandidateKnowledgeModel structured tracking and competency graph traversal.
4. Repetition avoidance and non-random follow-up selection.
"""
from __future__ import annotations

import pytest

from conversational_engine import (
    DialoguePolicy,
    CandidateKnowledgeModel,
    COMPETENCY_GRAPHS,
    select_graph_followup,
    INTENT_CLARIFICATION,
    INTENT_REPEAT,
    INTENT_UNCERTAINTY,
    INTENT_SKIP,
    INTENT_ANSWER,
)
from interview_state import InterviewStateMachine, InterviewState


def test_dialogue_policy_intent_classification():
    # Clarification
    assert DialoguePolicy.classify_intent("Could you please clarify the question?") == INTENT_CLARIFICATION
    assert DialoguePolicy.classify_intent("What do you mean by that?") == INTENT_CLARIFICATION
    assert DialoguePolicy.classify_intent("దయచేసి ఈ ప్రశ్నను మరింత వివరించండి") == INTENT_CLARIFICATION
    assert DialoguePolicy.classify_intent("क्या आप यह सवाल स्पष्ट कर सकते हैं?") == INTENT_CLARIFICATION

    # Repeat
    assert DialoguePolicy.classify_intent("Can you repeat the question please?") == INTENT_REPEAT
    assert DialoguePolicy.classify_intent("Please say that again") == INTENT_REPEAT
    assert DialoguePolicy.classify_intent("మళ్లీ చెప్పండి") == INTENT_REPEAT
    assert DialoguePolicy.classify_intent("कृपया सवाल दोहराएं") == INTENT_REPEAT

    # Uncertainty
    assert DialoguePolicy.classify_intent("I don't know the answer to this.") == INTENT_UNCERTAINTY
    assert DialoguePolicy.classify_intent("I am not sure about this concept.") == INTENT_UNCERTAINTY
    assert DialoguePolicy.classify_intent("నాకు ఈ విషయం తెలియదు") == INTENT_UNCERTAINTY
    assert DialoguePolicy.classify_intent("मुझे इसकी जानकारी नहीं है") == INTENT_UNCERTAINTY

    # Skip
    assert DialoguePolicy.classify_intent("Can we skip this question?") == INTENT_SKIP
    assert DialoguePolicy.classify_intent("Skip please") == INTENT_SKIP
    assert DialoguePolicy.classify_intent("ఈ ప్రశ్నను దాటవేయండి") == INTENT_SKIP
    assert DialoguePolicy.classify_intent("अगला सवाल पूछें, इसे छोड़ दें") == INTENT_SKIP

    # Substantive answer should NOT be classified as intent
    ans1 = "In my project I used FastAPI with Redis caching to improve database throughput and reduce latency."
    assert DialoguePolicy.classify_intent(ans1) == INTENT_ANSWER
    ans2 = "I configured Docker containers and wrote unit tests using pytest with 90 percent coverage."
    assert DialoguePolicy.classify_intent(ans2) == INTENT_ANSWER


def test_clarification_does_not_advance_or_penalize_candidate():
    sm = InterviewStateMachine(track="software", language="en-IN")
    sm.transition(InterviewState.asking)
    initial_q = sm.current_question_text()
    assert sm.question_index == 0

    # Candidate asks for clarification
    result = sm.process_candidate_utterance("Could you explain what you mean by that question?")
    assert result["intent"] == INTENT_CLARIFICATION
    assert result["advance"] is False
    assert result["completed"] is False
    assert sm.question_index == 0
    assert sm.current_question_text() == initial_q
    assert len(sm.answers) == 0
    assert "Here is what I'm asking" in result["response_text"]


def test_repeat_does_not_advance_or_penalize_candidate():
    sm = InterviewStateMachine(track="agentic", language="te-IN")
    sm.transition(InterviewState.asking)
    initial_q = sm.current_question_text()
    assert sm.question_index == 0

    # Candidate asks to repeat in Telugu
    result = sm.process_candidate_utterance("మళ్లీ చెప్పండి")
    assert result["intent"] == INTENT_REPEAT
    assert result["advance"] is False
    assert sm.question_index == 0
    assert sm.current_question_text() == initial_q
    assert len(sm.answers) == 0
    assert "మళ్లీ చెబుతున్నాను" in result["response_text"]


def test_uncertainty_pivots_gracefully_without_zero_score():
    sm = InterviewStateMachine(track="ai", language="hi-IN")
    sm.transition(InterviewState.asking)
    assert sm.question_index == 0

    result = sm.process_candidate_utterance("मुझे नहीं पता")
    assert result["intent"] == INTENT_UNCERTAINTY
    assert result["advance"] is True
    assert sm.question_index == 1
    assert len(sm.answers) == 1
    fb = result["feedback"]
    assert fb["status"] == "uncertain"
    # Should not be a punishing 0 score
    assert fb["score"] > 0
    assert "कोई बात नहीं" in result["response_text"]


def test_skip_records_cleanly_and_advances():
    sm = InterviewStateMachine(track="software", language="en-IN")
    sm.transition(InterviewState.asking)
    assert sm.question_index == 0

    result = sm.process_candidate_utterance("Can we please skip this question?")
    assert result["intent"] == INTENT_SKIP
    assert result["advance"] is True
    assert sm.question_index == 1
    assert len(sm.answers) == 1
    fb = result["feedback"]
    assert fb["status"] == "skipped"
    assert "Moving on" in result["response_text"]


def test_candidate_knowledge_model_tracking_and_graph_traversal():
    km = CandidateKnowledgeModel(role="Distributed Systems Engineer", track="software", difficulty="applied")

    # Record strong answer
    feedback_strong = {
        "score": 85,
        "dimensions": {"technical_coverage": 28, "tradeoff": 24, "evidence": 20, "clarity": 18},
        "missing_concepts": [],
        "risks": [],
    }
    km.record_answer_turn(
        turn_index=0,
        question_text="Describe your bug fix",
        concept="coroutines",
        feedback=feedback_strong,
        transcript="I refactored the blocking synchronous HTTP calls to use httpx with asyncio gather.",
    )

    state = km.competencies["coroutines"]
    assert state.status == "demonstrated"
    assert state.confidence > 0.8
    assert len(km.decisions) == 1
    assert km.decisions[0]["status"] == "demonstrated"

    # Select next question via graph
    spec, reason, focus = select_graph_followup(km, "en-IN", feedback_strong)
    # Should escalate to architecture tier
    assert spec["level"] == "architecture"
    assert km.current_difficulty == "architecture"

    # Record misconception answer
    feedback_misconception = {
        "score": 30,
        "dimensions": {"technical_coverage": 8, "tradeoff": 5, "evidence": 5, "clarity": 12},
        "missing_concepts": ["gil_release"],
        "risks": [{"code": "known_metric_confusion", "quote": "accuracy is always 100%", "explanation": "Overfitting risk"}],
    }
    km.record_answer_turn(
        turn_index=1,
        question_text="Explain failover",
        concept="distributed_reliability",
        feedback=feedback_misconception,
        transcript="My system had 100% accuracy and never had any errors.",
    )

    state_dist = km.competencies["distributed_reliability"]
    assert state_dist.status == "misconception"

    # Follow-up should de-escalate to fundamentals
    spec2, reason2, focus2 = select_graph_followup(km, "en-IN", feedback_misconception)
    assert spec2["level"] == "fundamentals"
    assert km.current_difficulty == "fundamentals"
