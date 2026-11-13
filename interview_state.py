"""Interview state machine for realtime voice sessions.

States: waiting → asking → listening → transcribing → review → feedback → followup → completed
Evon integration is unreachable: kept as a constant so callers can check.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from coach import QUESTION_BANK
from adaptive import select_followup
from robust_evaluation import evaluate_for_app

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


# Allowed state transitions (source → set of valid targets)
_TRANSITIONS: dict[InterviewState, set[InterviewState]] = {
    InterviewState.waiting:      {InterviewState.asking},
    InterviewState.asking:       {InterviewState.listening},
    InterviewState.listening:    {InterviewState.transcribing, InterviewState.asking},
    InterviewState.transcribing: {InterviewState.review},
    InterviewState.review:       {InterviewState.feedback},
    InterviewState.feedback:     {InterviewState.followup, InterviewState.completed},
    InterviewState.followup:     {InterviewState.asking},
    InterviewState.completed:    set(),
}


class InvalidTransition(ValueError):
    """Raised when a state transition is not allowed."""


class InterviewStateMachine:
    """Tracks the state of a single realtime interview session."""

    MAX_QUESTIONS = 3

    def __init__(self, track: str, language: str) -> None:
        if track not in QUESTION_BANK:
            raise ValueError(f"Unknown track: {track}")
        self.track = track
        self.language = language
        self._state = InterviewState.waiting
        self._turn_id = str(uuid.uuid4())
        self.question_index: int = 0

        # Transcript tracking
        self.provider_transcript: str = ""
        self.edited_transcript: str = ""
        self.consent_given: bool = False

        # Question state
        self.pending_question: Optional[dict] = None
        self.pending_kind: str = "core"
        self.pending_reason: str = ""

        # Accumulated answers
        self.answers: list[dict] = []

    # -- properties ----------------------------------------------------------

    @property
    def current_state(self) -> InterviewState:
        return self._state

    @property
    def turn_id(self) -> str:
        return self._turn_id

    @property
    def is_complete(self) -> bool:
        return self._state == InterviewState.completed

    # -- transitions ---------------------------------------------------------

    def transition(self, new_state: InterviewState) -> InterviewState:
        """Move to *new_state*; raises InvalidTransition on illegal moves."""
        if isinstance(new_state, str):
            new_state = InterviewState(new_state)
        allowed = _TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise InvalidTransition(
                f"Cannot transition from {self._state.value} to {new_state.value}"
            )
        self._state = new_state
        if new_state == InterviewState.asking:
            # New turn for each question
            self._turn_id = str(uuid.uuid4())
            self.provider_transcript = ""
            self.edited_transcript = ""
        return self._state

    def cancel(self) -> InterviewState:
        """Reset to waiting (e.g. on disconnect or user abort)."""
        self._state = InterviewState.waiting
        self._turn_id = str(uuid.uuid4())
        self.provider_transcript = ""
        self.edited_transcript = ""
        return self._state

    # -- question helpers ----------------------------------------------------

    def current_question_spec(self) -> Optional[dict]:
        """Return the current question dict or None if done."""
        if self.question_index >= self.MAX_QUESTIONS:
            return None
        if self.pending_question is not None:
            return self.pending_question
        return QUESTION_BANK[self.track][0]

    def current_question_text(self) -> Optional[str]:
        spec = self.current_question_spec()
        return spec[self.language] if spec else None

    # -- evaluation ----------------------------------------------------------

    def evaluate_answer(self, transcript: str) -> dict:
        """Score a transcript using the risk-aware rubric.

        Feedback is labelled as uncalibrated practice guidance.
        """
        q = self.current_question_spec()
        if q is None:
            raise RuntimeError("No active question to evaluate.")

        fixed_index = (
            0 if self.question_index == 0
            else 1 if self.question_index == 2
            else None
        )
        feedback = evaluate_for_app(
            transcript, q, self.language, self.track, fixed_index
        )
        feedback["label"] = FEEDBACK_LABEL
        return feedback

    def advance(self, transcript: str) -> dict:
        """Evaluate the answer, record it and advance to the next question.

        Returns the feedback dict (including any follow-up question info).
        """
        q = self.current_question_spec()
        if q is None:
            raise RuntimeError("Interview already complete.")

        feedback = self.evaluate_answer(transcript)
        qtext = q[self.language]

        self.answers.append({
            "question": qtext,
            "question_kind": self.pending_kind,
            "question_reason": self.pending_reason,
            "transcript": transcript,
            "feedback": feedback,
        })
        self.question_index += 1

        done = self.question_index >= self.MAX_QUESTIONS

        if self.question_index == 1:
            question, reason, focus = select_followup(
                self.track, self.language, feedback
            )
            self.pending_question = question
            self.pending_kind = "adaptive"
            self.pending_reason = reason
            feedback["follow_up"] = question[self.language]
            feedback["follow_up_focus"] = focus
        elif self.question_index == 2:
            self.pending_question = QUESTION_BANK[self.track][1]
            self.pending_kind = "core"
            self.pending_reason = "Returning to a separate topic for broader practice."
            feedback["follow_up"] = self.pending_question[self.language]
        else:
            self.pending_question = None
            self.pending_kind = "complete"
            self.pending_reason = ""

        feedback["completed"] = done
        feedback["answered"] = self.question_index
        feedback["total_questions"] = self.MAX_QUESTIONS
        return feedback
