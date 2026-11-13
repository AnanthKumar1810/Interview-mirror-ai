import pytest
from interview_state import (
    InterviewState,
    InterviewStateMachine,
    InvalidTransition,
    EVON_AVAILABLE,
    FEEDBACK_LABEL,
)


def test_evon_is_always_unavailable():
    assert EVON_AVAILABLE is False


def test_initialization():
    sm = InterviewStateMachine(track="agentic", language="en-IN")
    assert sm.current_state == InterviewState.waiting
    assert sm.track == "agentic"
    assert sm.language == "en-IN"
    assert sm.question_index == 0
    assert sm.consent_given is False
    assert sm.provider_transcript == ""
    assert sm.edited_transcript == ""
    assert sm.is_complete is False
    assert sm.turn_id is not None

    with pytest.raises(ValueError):
        InterviewStateMachine(track="nonexistent_track", language="en-IN")


def test_valid_state_transitions():
    sm = InterviewStateMachine(track="agentic", language="en-IN")

    # waiting -> asking
    initial_turn_id = sm.turn_id
    assert sm.transition(InterviewState.asking) == InterviewState.asking
    assert sm.turn_id != initial_turn_id  # asking regenerates turn_id

    # asking -> listening
    assert sm.transition(InterviewState.listening) == InterviewState.listening

    # listening -> transcribing
    assert sm.transition(InterviewState.transcribing) == InterviewState.transcribing

    # transcribing -> review
    assert sm.transition(InterviewState.review) == InterviewState.review

    # review -> feedback
    assert sm.transition(InterviewState.feedback) == InterviewState.feedback

    # feedback -> followup
    assert sm.transition(InterviewState.followup) == InterviewState.followup

    # followup -> asking
    assert sm.transition(InterviewState.asking) == InterviewState.asking

    # listening can also transition back to asking (e.g. barge-in or re-ask)
    assert sm.transition(InterviewState.listening) == InterviewState.listening
    assert sm.transition(InterviewState.asking) == InterviewState.asking

    # Transitioning using string literals
    sm.transition("listening")
    assert sm.current_state == InterviewState.listening
    sm.transition("transcribing")
    sm.transition("review")
    sm.transition("feedback")

    # feedback -> completed
    assert sm.transition(InterviewState.completed) == InterviewState.completed
    assert sm.is_complete is True


def test_invalid_state_transitions():
    sm = InterviewStateMachine(track="agentic", language="en-IN")
    assert sm.current_state == InterviewState.waiting

    # Illegal from waiting: can only go to asking
    for invalid in [
        InterviewState.listening,
        InterviewState.transcribing,
        InterviewState.review,
        InterviewState.feedback,
        InterviewState.followup,
        InterviewState.completed,
    ]:
        with pytest.raises(InvalidTransition):
            sm.transition(invalid)

    # Illegal from completed: terminal state
    sm.transition(InterviewState.asking)
    sm.transition(InterviewState.listening)
    sm.transition(InterviewState.transcribing)
    sm.transition(InterviewState.review)
    sm.transition(InterviewState.feedback)
    sm.transition(InterviewState.completed)

    for target in InterviewState:
        with pytest.raises(InvalidTransition):
            sm.transition(target)


def test_cancel_resets_to_waiting():
    sm = InterviewStateMachine(track="agentic", language="en-IN")
    sm.transition(InterviewState.asking)
    sm.transition(InterviewState.listening)

    sm.provider_transcript = "Raw voice transcript"
    sm.edited_transcript = "Corrected transcript"
    old_turn = sm.turn_id

    reset_state = sm.cancel()
    assert reset_state == InterviewState.waiting
    assert sm.current_state == InterviewState.waiting
    assert sm.turn_id != old_turn
    assert sm.provider_transcript == ""
    assert sm.edited_transcript == ""


def test_transcript_storage_and_consent_tracking():
    sm = InterviewStateMachine(track="agentic", language="en-IN")
    assert sm.consent_given is False

    sm.consent_given = True
    assert sm.consent_given is True

    # Storage of separate provider vs edited transcripts
    sm.provider_transcript = "i used python to build a agent"
    sm.edited_transcript = "I used Python to build an agent."

    assert sm.provider_transcript != sm.edited_transcript
    assert sm.provider_transcript == "i used python to build a agent"
    assert sm.edited_transcript == "I used Python to build an agent."

    # When transitioning to asking, transcripts reset for new question turn
    sm.transition(InterviewState.asking)
    assert sm.provider_transcript == ""
    assert sm.edited_transcript == ""


def test_advance_and_evaluation_flow():
    sm = InterviewStateMachine(track="agentic", language="en-IN")

    q1_text = sm.current_question_text()
    assert q1_text is not None and len(q1_text) > 0

    # Question 1: advance creates feedback and selects adaptive follow-up
    fb1 = sm.advance("I built an agent using Python with a tool calling pattern and tests.")
    assert fb1["label"] == FEEDBACK_LABEL
    assert fb1["label"] == "uncalibrated practice guidance"
    assert fb1["answered"] == 1
    assert fb1["completed"] is False
    assert "follow_up" in fb1
    assert sm.pending_kind == "adaptive"

    # Question 2: advance creates feedback and moves to 3rd core question
    fb2 = sm.advance("I tested edge cases and mocked API calls to ensure resilience.")
    assert fb2["answered"] == 2
    assert fb2["completed"] is False
    assert sm.pending_kind == "core"

    # Question 3: advance creates final feedback and marks completed
    fb3 = sm.advance("For deployment I used Docker with health checks and structured logs.")
    assert fb3["answered"] == 3
    assert fb3["completed"] is True
    assert sm.pending_kind == "complete"
    assert sm.current_question_spec() is None
    assert sm.current_question_text() is None

    # Advance after completion raises RuntimeError
    with pytest.raises(RuntimeError):
        sm.advance("Another answer")
