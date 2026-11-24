"""Synthetic RTC callback replay; times are constructed, not acoustic measurements."""
from __future__ import annotations

import json
from pathlib import Path
from rtc_turn_lab import TurnLab, percentile


class FakeSpeechHandle:
    def __init__(self):
        self.interruptions = 0

    def interrupt(self):
        self.interruptions += 1


def replay_case(case: dict) -> dict:
    lab, handle = TurnLab(), FakeSpeechHandle()
    lab.active_speech = handle
    action = None
    for event in case["events"]:
        kind = event["kind"]
        if kind == "agent_state":
            lab.agent_state(event["state"], at=event["at"])
        elif kind == "user_state":
            lab.user_state(event["state"], at=event["at"])
        elif kind == "interruption_detected":
            lab.interruption_detected()
        elif kind == "false_interruption":
            lab.false_interruption()
        elif kind == "transcript":
            action = lab.classify(event["text"])
        else:
            raise ValueError(f"Unknown callback: {kind}")
    return {"id": case["id"], "actual": action,
            "pass": action == case["expected_action"] and
                    handle.interruptions == case["expected_cancellations"],
            "cancellations": handle.interruptions,
            "overlap_samples_ms": list(lab.overlap_to_yield_ms),
            **lab.summary()}


def run_replay(cases: list[dict]) -> dict:
    results = [replay_case(case) for case in cases]
    samples = [sample for result in results for sample in result["overlap_samples_ms"]]
    return {"cases": len(results), "passed": sum(result["pass"] for result in results),
            "overlap_to_yield_ms": {"n": len(samples), "p50": percentile(samples, .5),
                                    "p95": percentile(samples, .95)},
            "results": results,
            "note": "Synthetic callbacks only; no microphone, LiveKit, Gnani, or real latency measured."}


if __name__ == "__main__":
    cases = json.loads((Path(__file__).parent / "datasets" /
                        "rtc_turn_scenarios.json").read_text(encoding="utf-8"))
    print(json.dumps(run_replay(cases), indent=2))
