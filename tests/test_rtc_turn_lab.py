import json
from pathlib import Path

from eval_harness.rtc_turn_replay import FakeSpeechHandle, replay_case, run_replay
from rtc_turn_lab import TurnLab, percentile, save_summary


def test_scripted_overlap_and_cancellation():
    cases = json.loads((Path(__file__).parents[1] / "eval_harness" / "datasets" /
                        "rtc_turn_scenarios.json").read_text(encoding="utf-8"))
    report = run_replay(cases)
    assert report["cases"] == report["passed"] == 6
    assert report["overlap_to_yield_ms"] == {"n": 4, "p50": 220, "p95": 350}


def test_late_transcript_keeps_overlap_and_short_answer_is_valid():
    lab, handle = TurnLab(), FakeSpeechHandle()
    lab.active_speech = handle
    lab.agent_state("speaking", at=1)
    lab.user_state("speaking", at=2)
    lab.agent_state("listening", at=2.2)
    assert lab.classify("Please repeat the question") == "repeat"
    assert handle.interruptions == 1
    assert lab.classify("No") == "answer"


def test_backchannel_does_not_explicitly_cancel_speech():
    lab, handle = TurnLab(), FakeSpeechHandle()
    lab.active_speech = handle
    lab.agent_state("speaking", at=0)
    lab.user_state("speaking", at=1)
    assert lab.classify("okay.") == "backchannel"
    assert handle.interruptions == 0
    lab.user_state("speaking", at=2)
    assert lab.classify("Okay, but I disagree") == "answer"
    assert handle.interruptions == 1


def test_completed_or_already_interrupted_handle_is_not_counted():
    lab = TurnLab()
    handle = FakeSpeechHandle()
    handle.done = lambda: True
    lab.active_speech = handle
    assert not lab.cancel_speech()
    assert handle.interruptions == 0


def test_percentiles_and_anonymous_metrics(tmp_path):
    assert percentile([], .95) is None
    assert percentile([150, 220, 350], .5) == 220
    assert percentile([150, 220, 350], .95) == 350
    saved = save_summary(TurnLab().summary(), language="te-IN", mode="vad", folder=tmp_path)
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["counts"]["answers"] == 0
    assert "transcript" not in data and "session_id" not in data
    assert not replay_case({"id": "incorrect", "events": [{"kind": "transcript", "text": "No"}],
                            "expected_action": "backchannel", "expected_cancellations": 0})["pass"]
