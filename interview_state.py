"""Interview state machine for hands-free realtime voice sessions.

States:
  waiting → asking → listening → transcribing → review → feedback → followup → completed

Supports cancellation, graceful early completion ('End interview'), separate
provider vs candidate-edited transcripts, and post-call correction re-evaluation.
Evon integration remains unreachable behind EVON_AVAILABLE = False.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional, Any

from coach import QUESTION_BANK
from adaptive import select_followup
from robust_evaluation import evaluate_for_app
from personalization import INTRODUCE_YOURSELF_QUESTION
from conversational_engine import (
    CandidateKnowledgeModel,
    DialoguePolicy,
    select_graph_followup,
    INTENT_CLARIFICATION,
    INTENT_REPEAT,
    INTENT_UNCERTAINTY,
    INTENT_SKIP,
    INTENT_ANSWER,
)

EVON_AVAILABLE = False
FEEDBACK_LABEL = "uncalibrated practice guidance"


class InterviewState(str, Enum):
    waiting = "waiting"
    asking = "asking"
    listening = "listening"
    transcribing = "transcribing"
    review = "review"
    feedback = "feedback"
    followup = "followup"
    completed = "completed"


# Explicit state transitions
_TRANSITIONS: dict[InterviewState, set[InterviewState]] = {
    InterviewState.waiting:      {InterviewState.asking},
    InterviewState.asking:       {InterviewState.listening, InterviewState.completed},
    InterviewState.listening:    {InterviewState.transcribing, InterviewState.asking, InterviewState.completed},
    InterviewState.transcribing: {InterviewState.review, InterviewState.completed},
    InterviewState.review:       {InterviewState.feedback, InterviewState.completed},
    InterviewState.feedback:     {InterviewState.followup, InterviewState.completed},
    InterviewState.followup:     {InterviewState.asking, InterviewState.completed},
    InterviewState.completed:    set(),
}


class InvalidTransition(ValueError):
    """Raised when a state transition is not permitted."""


class InterviewStateMachine:
    """Deterministic controller for a hands-free interview session with conversational intelligence."""

    def __init__(
        self,
        track: str,
        language: str,
        max_questions: int = 3,
        role: str = "Software Engineer",
        initial_question_spec: Optional[dict] = None,
    ) -> None:
        if track not in QUESTION_BANK:
            raise ValueError(f"Unknown track: {track}")
        self.track = track
        self.language = language
        self.MAX_QUESTIONS = max_questions
        self.role = role
        self._state = InterviewState.waiting
        self._turn_id = str(uuid.uuid4())
        self.question_index: int = 0

        # Transcripts and consent
        self.provider_transcript: str = ""
        self.edited_transcript: str = ""
        self.consent_given: bool = False

        # Current question context
        self.personalized_seed: Optional[dict] = initial_question_spec
        self.pending_question: Optional[dict] = initial_question_spec
        self.pending_kind: str = "personalized_core" if initial_question_spec else "core"
        self.pending_reason: str = "Seeded from candidate background" if initial_question_spec else ""

        # Conversational Knowledge Model
        self.knowledge_model = CandidateKnowledgeModel(role=role, track=track)

        # Accumulated answers
        self.answers: list[dict[str, Any]] = []

    @property
    def current_state(self) -> InterviewState:
        return self._state

    @property
    def turn_id(self) -> str:
        return self._turn_id

    @property
    def is_complete(self) -> bool:
        return self._state == InterviewState.completed

    def transition(self, new_state: InterviewState | str) -> InterviewState:
        """Advance to new_state; raises InvalidTransition if not permitted."""
        if isinstance(new_state, str):
            new_state = InterviewState(new_state)
        allowed = _TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise InvalidTransition(
                f"Cannot transition from {self._state.value} to {new_state.value}"
            )
        self._state = new_state
        if new_state == InterviewState.asking:
            self._turn_id = str(uuid.uuid4())
            self.provider_transcript = ""
            self.edited_transcript = ""
        return self._state

    def cancel(self) -> InterviewState:
        """Reset state machine to waiting (abort or disconnect)."""
        self._state = InterviewState.waiting
        self._turn_id = str(uuid.uuid4())
        self.provider_transcript = ""
        self.edited_transcript = ""
        return self._state

    def end_interview(self) -> InterviewState:
        """Gracefully complete interview early on candidate request."""
        self._state = InterviewState.completed
        return self._state

    def current_question_spec(self) -> Optional[dict]:
        """Return the current question dict specification or None if complete."""
        if self.question_index >= self.MAX_QUESTIONS:
            return None
        if self.pending_question is not None:
            return self.pending_question
        return QUESTION_BANK[self.track][0]

    def current_question_text(self) -> Optional[str]:
        spec = self.current_question_spec()
        if not spec:
            return None
        return spec.get(self.language) or spec.get("text")

    def evaluate_answer(self, transcript: str) -> dict:
        """Evaluate transcript using deterministic practice rubric."""
        q = self.current_question_spec()
        if q is None:
            raise RuntimeError("No active question to evaluate.")

        fixed_index = (
            0 if self.question_index == 0 and self.pending_kind == "core"
            else 1 if self.question_index == 2 and self.pending_kind == "core"
            else None
        )
        feedback = evaluate_for_app(
            transcript, q, self.language, self.track, fixed_index
        )
        feedback["label"] = FEEDBACK_LABEL
        return feedback

    def _select_next_question(self, feedback: dict) -> None:
        """Select next question spec and transparent reason."""
        if self.question_index == 1:
            if self.personalized_seed:
                self.pending_question = self.personalized_seed
                self.pending_kind = "personalized_project"
                self.pending_reason = "Technical question tailored to candidate GitHub project"
                feedback["follow_up"] = self.pending_question.get(self.language) or self.pending_question.get("text")
            else:
                question, reason, focus = select_followup(
                    self.track, self.language, feedback
                )
                self.pending_question = question
                self.pending_kind = "adaptive"
                self.pending_reason = reason
                feedback["follow_up"] = question[self.language]
                feedback["follow_up_focus"] = focus
        elif self.question_index == 2 and self.MAX_QUESTIONS == 3:
            if self.personalized_seed and self.personalized_seed.get("achievement_question"):
                self.pending_question = self.personalized_seed["achievement_question"]
                self.pending_kind = "personalized_achievement"
                self.pending_reason = "Deep dive into candidate's demonstrated achievement from resume"
                feedback["follow_up"] = self.pending_question.get(self.language) or self.pending_question.get("text")
            else:
                self.pending_question = QUESTION_BANK[self.track][1]
                self.pending_kind = "core"
                self.pending_reason = "Returning to a separate topic for broader practice."
                feedback["follow_up"] = self.pending_question[self.language]
        elif self.question_index < self.MAX_QUESTIONS:
            question, reason, focus = select_graph_followup(
                self.knowledge_model, self.language, feedback
            )
            self.pending_question = question
            self.pending_kind = "adaptive"
            self.pending_reason = reason
            feedback["follow_up"] = question[self.language]
            feedback["follow_up_focus"] = focus
        else:
            self.pending_question = None
            self.pending_kind = "complete"
            self.pending_reason = ""

    def advance(self, transcript: str, *, provider_text: Optional[str] = None) -> dict:
        """Score answer, record turn, select next question, and advance index.

        Idempotency: If this turn_id has already been committed, returns the
        existing feedback without double-advancing or duplicate scoring.
        """
        for a in self.answers:
            if a.get("turn_id") == self._turn_id:
                return a["feedback"]

        q = self.current_question_spec()
        if q is None:
            raise RuntimeError("Interview already complete.")

        feedback = self.evaluate_answer(transcript)
        qtext = q.get(self.language) or q.get("text", "")
        concept = q.get("keywords", ["general"])[0] if q and q.get("keywords") else "general"

        turn_record = {
            "turn_id": self._turn_id,
            "question": qtext,
            "question_kind": self.pending_kind,
            "question_reason": self.pending_reason,
            "question_spec": q,
            "provider_transcript": provider_text or self.provider_transcript or transcript,
            "transcript": transcript,
            "edited_transcript": self.edited_transcript or None,
            "feedback": feedback,
        }
        self.answers.append(turn_record)

        # Update candidate knowledge model
        self.knowledge_model.record_answer_turn(
            self.question_index, qtext, concept, feedback, transcript
        )

        self.question_index += 1
        done = self.question_index >= self.MAX_QUESTIONS

        self._select_next_question(feedback)

        feedback["completed"] = done
        feedback["answered"] = self.question_index
        feedback["total_questions"] = self.MAX_QUESTIONS
        # Fresh turn_id for upcoming turn
        self._turn_id = str(uuid.uuid4())
        return feedback

    def process_candidate_utterance(
        self, transcript: str, *, provider_text: Optional[str] = None
    ) -> dict[str, Any]:
        """Process candidate speech through DialoguePolicy before rubric evaluation.

        Handles:
        - Clarification: Explains question without penalty, stays on current turn.
        - Repeat: Re-synthesizes question without penalty, stays on current turn.
        - Uncertainty: Acknowledges without penalizing, pivots to foundational concept.
        - Skip: Records clean skip and moves to next topic.
        - Answer: Standard answer evaluation and progression.
        """
        intent = DialoguePolicy.classify_intent(transcript)
        q = self.current_question_spec()
        qtext = q.get(self.language) or q.get("text", "") if q else ""
        concept = q.get("keywords", ["general"])[0] if q and q.get("keywords") else "general"

        if intent == INTENT_CLARIFICATION:
            clarification = DialoguePolicy.generate_clarification(qtext, self.language)
            self.knowledge_model.record_dialogue_event(
                self.question_index, intent, concept, "Candidate requested clarification"
            )
            return {
                "intent": intent,
                "action": "clarify",
                "advance": False,
                "response_text": clarification,
                "completed": False,
                "feedback": None,
            }
        elif intent == INTENT_REPEAT:
            repeat_text = DialoguePolicy.generate_repeat(qtext, self.language)
            self.knowledge_model.record_dialogue_event(
                self.question_index, intent, concept, "Candidate requested question repeat"
            )
            return {
                "intent": intent,
                "action": "repeat",
                "advance": False,
                "response_text": repeat_text,
                "completed": False,
                "feedback": None,
            }
        elif intent == INTENT_SKIP:
            turn_record = {
                "turn_id": self._turn_id,
                "question": qtext,
                "question_kind": self.pending_kind,
                "question_reason": "Skipped on candidate request",
                "provider_transcript": provider_text or self.provider_transcript or transcript,
                "transcript": transcript,
                "edited_transcript": None,
                "feedback": {
                    "score": 0,
                    "status": "skipped",
                    "label": FEEDBACK_LABEL,
                    "dimensions": {"technical_coverage": 0, "tradeoff": 0, "evidence": 0, "clarity": 0},
                    "missing_concepts": [concept],
                    "strengths": [],
                    "improvements": ["Question skipped by candidate"],
                },
            }
            self.answers.append(turn_record)
            self.knowledge_model.record_dialogue_event(
                self.question_index, intent, concept, "Candidate skipped question"
            )
            self.question_index += 1
            done = self.question_index >= self.MAX_QUESTIONS
            self._select_next_question(turn_record["feedback"])
            ack = DialoguePolicy.generate_skip_ack(self.language)
            self._turn_id = str(uuid.uuid4())
            return {
                "intent": intent,
                "action": "skip",
                "advance": True,
                "response_text": ack,
                "completed": done,
                "feedback": turn_record["feedback"],
            }
        elif intent == INTENT_UNCERTAINTY:
            feedback = {
                "score": 25,
                "status": "uncertain",
                "label": FEEDBACK_LABEL,
                "dimensions": {"technical_coverage": 5, "tradeoff": 5, "evidence": 5, "clarity": 10},
                "missing_concepts": [concept],
                "strengths": ["Honest assessment of current knowledge"],
                "improvements": [f"Review foundational mechanisms for {concept}"],
            }
            turn_record = {
                "turn_id": self._turn_id,
                "question": qtext,
                "question_kind": self.pending_kind,
                "question_reason": "Candidate expressed uncertainty; grounding in fundamentals",
                "provider_transcript": provider_text or self.provider_transcript or transcript,
                "transcript": transcript,
                "edited_transcript": None,
                "feedback": feedback,
            }
            self.answers.append(turn_record)
            self.knowledge_model.record_dialogue_event(
                self.question_index, intent, concept, "Candidate expressed uncertainty"
            )
            self.question_index += 1
            done = self.question_index >= self.MAX_QUESTIONS
            self._select_next_question(feedback)
            pivot_text = DialoguePolicy.generate_uncertainty_pivot(self.language)
            self._turn_id = str(uuid.uuid4())
            return {
                "intent": intent,
                "action": "uncertainty_pivot",
                "advance": True,
                "response_text": pivot_text,
                "completed": done,
                "feedback": feedback,
            }
        else:
            feedback = self.advance(transcript, provider_text=provider_text)
            return {
                "intent": INTENT_ANSWER,
                "action": "evaluate",
                "advance": True,
                "response_text": None,
                "completed": feedback.get("completed", False),
                "feedback": feedback,
            }

    def correct_answer(self, question_idx: int, corrected_text: str) -> dict:
        """Re-evaluate an answer when corrected by the candidate post-interview."""
        if not (0 <= question_idx < len(self.answers)):
            raise IndexError("Invalid answer index to correct.")

        corrected = corrected_text.strip()
        if len(corrected) < 3:
            raise ValueError("Corrected transcript is too short.")

        record = self.answers[question_idx]
        record["edited_transcript"] = corrected
        record["transcript"] = corrected

        # Find original question spec to re-evaluate
        spec = record.get("question_spec")
        if spec is None:
            spec = QUESTION_BANK[self.track][0] if question_idx == 0 else (
                QUESTION_BANK[self.track][1] if question_idx == 2 else None
            )
        # If adaptive follow-up, re-evaluate with current stored question text
        if spec is None:
            spec = {"keywords": []}
            spec[self.language] = record["question"]

        fixed_index = 0 if question_idx == 0 else 1 if question_idx == 2 else None
        new_feedback = evaluate_for_app(corrected, spec, self.language, self.track, fixed_index)
        new_feedback["label"] = FEEDBACK_LABEL
        record["feedback"] = new_feedback
        return record
