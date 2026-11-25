"""RTC turn decisions and callback metrics; never store audio or transcripts."""
from __future__ import annotations

import json
import math
import os
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from rtc_policy import is_backchannel

REPEAT_COMMANDS = frozenset({
    "repeat", "repeat that", "please repeat", "repeat the question",
    "please repeat the question", "could you repeat the question",
    "can you repeat the question", "say that again", "please say that again",
    "फिर से बोलिए", "दोबारा बताइए", "सवाल दोहराएं", "सवाल दोहराएँ",
    "मुझे सवाल फिर से बताइए", "మళ్లీ చెప్పండి", "మళ్ళీ చెప్పండి",
    "మరోసారి చెప్పండి", "ప్రశ్న మళ్లీ అడగండి", "మళ్ళీ అడగండి",
})


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)], 2)


@dataclass
class TurnLab:
    clock: Callable[[], float] = time.monotonic
    agent_speaking: bool = False
    overlapped: bool = False
    overlap_started: float | None = None
    user_stopped: float | None = None
    active_speech: object | None = None
    counts: dict[str, int] = field(default_factory=lambda: {
        "answers": 0, "backchannels": 0, "repeat_requests": 0,
        "detected_interruptions": 0, "sdk_false_interruptions": 0,
        "explicit_speech_cancellations": 0,
    })
    overlap_to_yield_ms: list[float] = field(default_factory=list)
    response_gap_ms: list[float] = field(default_factory=list)

    def agent_state(self, state: str, *, at: float | None = None) -> None:
        now = self.clock() if at is None else at
        speaking = state == "speaking"
        if self.agent_speaking and not speaking and self.overlap_started is not None:
            self.overlap_to_yield_ms.append(max(0, (now - self.overlap_started) * 1000))
            self.overlap_started = None
        if not self.agent_speaking and speaking and self.user_stopped is not None:
            self.response_gap_ms.append(max(0, (now - self.user_stopped) * 1000))
            self.user_stopped = None
        self.agent_speaking = speaking

    def user_state(self, state: str, *, at: float | None = None) -> None:
        now = self.clock() if at is None else at
        if state == "speaking" and self.agent_speaking:
            self.overlapped = True
            if self.overlap_started is None:
                self.overlap_started = now
        elif state == "listening":
            self.user_stopped = now

    def interruption_detected(self) -> None:
        self.counts["detected_interruptions"] += 1

    def false_interruption(self) -> None:
        self.counts["sdk_false_interruptions"] += 1

    def classify(self, text: str) -> str:
        normalized = " ".join(unicodedata.normalize("NFC", text.casefold()).split()).strip(".,!?।॥ ")
        during_speech = self.overlapped or self.agent_speaking
        self.overlapped = False
        if not normalized:
            return "empty"
        if is_backchannel(normalized, during_speech):
            self.counts["backchannels"] += 1
            return "backchannel"
        if normalized in REPEAT_COMMANDS:
            self.counts["repeat_requests"] += 1
            if during_speech:
                self.cancel_speech()
            return "repeat"
        self.counts["answers"] += 1
        if during_speech:
            self.cancel_speech()
        return "answer"

    def cancel_speech(self) -> bool:
        handle = self.active_speech
        if handle is None:
            return False
        self.active_speech = None
        done = getattr(handle, "done", None)
        if callable(done) and done():
            return False
        if getattr(handle, "interrupted", False):
            return False
        try:
            handle.interrupt()  # LiveKit SpeechHandle cancels actual playback.
        except RuntimeError:
            return False  # The SDK may already have stopped this handle.
        self.counts["explicit_speech_cancellations"] += 1
        return True

    def summary(self) -> dict:
        return {
            "counts": dict(self.counts),
            "overlap_to_yield_ms": {
                "n": len(self.overlap_to_yield_ms),
                "p50": percentile(self.overlap_to_yield_ms, .5),
                "p95": percentile(self.overlap_to_yield_ms, .95),
            },
            "response_gap_ms": {
                "n": len(self.response_gap_ms),
                "p50": percentile(self.response_gap_ms, .5),
                "p95": percentile(self.response_gap_ms, .95),
            },
            "measurement_note": "SDK callback intervals; acoustic latency and missed interruptions require labelled audio runs",
        }


def save_summary(summary: dict, *, language: str, mode: str, folder: str | Path) -> Path:
    """Atomic anonymous aggregate: no transcript, audio, or session ID."""
    directory = Path(folder)
    directory.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    final, temp = directory / f"{name}.json", directory / f"{name}.tmp"
    try:
        with open(temp, "x", encoding="utf-8") as stream:
            json.dump({"language": language, "interruption_mode": mode, **summary}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, final)
    finally:
        temp.unlink(missing_ok=True)
    return final
