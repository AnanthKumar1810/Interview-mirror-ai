"""Transport-independent turn policy for the optional RTC interview."""
from __future__ import annotations

from dataclasses import dataclass, field

SUPPORTED_LANGUAGES = frozenset({"en-IN", "hi-IN", "te-IN"})
SEMANTIC_LANGUAGES = frozenset({"en-IN", "hi-IN"})
BACKCHANNELS = frozenset({"yes", "yeah", "yep", "okay", "ok", "hmm", "uh huh", "हाँ", "हां", "ठीक", "అవును", "సరే"})


def turn_mode(language: str) -> str:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("Unsupported interview language")
    return "multilingual" if language in SEMANTIC_LANGUAGES else "vad"


def is_backchannel(text: str, agent_speaking: bool) -> bool:
    return agent_speaking and " ".join(text.casefold().split()).strip(".,!?।") in BACKCHANNELS


@dataclass
class TurnLedger:
    """Reject repeats and stale work after the question or speech generation changes."""

    question_number: int = 1
    generation: int = 0
    processed: set[tuple[int, str]] = field(default_factory=set)
    closed: bool = False

    def start(self, question_number: int, transcript: str) -> int | None:
        key = (question_number, " ".join(transcript.casefold().split()))
        if self.closed or question_number != self.question_number or not key[1] or key in self.processed:
            return None
        self.processed.add(key)
        self.generation += 1
        return self.generation

    def advance(self, generation: int, question_number: int) -> bool:
        if self.closed or generation != self.generation or question_number != self.question_number:
            return False
        self.question_number += 1
        return True

    def valid_audio(self, generation: int) -> bool:
        return not self.closed and generation == self.generation

    def cancel(self) -> None:
        self.generation += 1

    def close(self) -> None:
        self.closed = True
        self.cancel()
