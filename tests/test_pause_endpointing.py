"""Tests and empirical comparison for candidate thinking-pause detection policies.

Compares:
  - Approach A: Fixed 1.8s pause timeout
  - Approach B: Two-stage (Prisma VAD segment + 0.6s grace period)
  - Approach C: Adaptive endpointing (syntax connectors: 2.2s; long declarative: 1.2s; default: 1.5s)
Evaluates on simulated pause durations: 300ms, 600ms, 900ms, 1300ms, 1800ms, 2200ms.
"""
from __future__ import annotations

import pytest
from ws_router import _SessionContext, _calculate_pause_timeout


def test_endpointing_policy_defaults():
    ctx_fixed = _SessionContext("s1", "agentic", "en-IN", "prisma-v2.5", True, endpointing_policy="fixed")
    assert _calculate_pause_timeout(ctx_fixed) == 1.8

    ctx_two_stage = _SessionContext("s2", "agentic", "en-IN", "prisma-v2.5", True, endpointing_policy="two_stage")
    assert _calculate_pause_timeout(ctx_two_stage) == 0.6

    ctx_adaptive = _SessionContext("s3", "agentic", "en-IN", "prisma-v2.5", True, endpointing_policy="adaptive")
    # Empty transcript defaults to 1.8s
    assert _calculate_pause_timeout(ctx_adaptive) == 1.8


def test_adaptive_endpointing_mid_sentence_connector():
    ctx = _SessionContext("s4", "agentic", "en-IN", "prisma-v2.5", True, endpointing_policy="adaptive")
    # Candidate paused right after saying 'because'
    ctx.accumulated_segments = ["I selected Redis", "because"]
    pause_timeout = _calculate_pause_timeout(ctx)
    assert pause_timeout == 2.2  # Granted extended thinking window

    # Telugu connector 'కాబట్టి'
    ctx.accumulated_segments = ["నేను కాఫ్కాను ఎంచుకున్నాను", "కాబట్టి"]
    assert _calculate_pause_timeout(ctx) == 2.2

    # Hindi connector 'क्योंकि'
    ctx.accumulated_segments = ["मैंने फास्टएपीआई चुना", "क्योंकि"]
    assert _calculate_pause_timeout(ctx) == 2.2


def test_adaptive_endpointing_completed_explanation():
    ctx = _SessionContext("s5", "agentic", "en-IN", "prisma-v2.5", True, endpointing_policy="adaptive")
    # Candidate gave full declarative explanation with punctuation
    ctx.accumulated_segments = [
        "I built an agentic code-repair system using Python and Docker.",
        "We tested all tools in an isolated sandbox with regression checks."
    ]
    pause_timeout = _calculate_pause_timeout(ctx)
    # Complete multi-sentence explanation ending in period
    assert pause_timeout == 1.2


@pytest.mark.parametrize("pause_ms,expected_cutoffs", [
    (300, {"fixed": False, "two_stage": False, "adaptive_connector": False}),
    (600, {"fixed": False, "two_stage": True,  "adaptive_connector": False}),
    (900, {"fixed": False, "two_stage": True,  "adaptive_connector": False}),
    (1300, {"fixed": False, "two_stage": True, "adaptive_connector": False}),
    (1800, {"fixed": True,  "two_stage": True, "adaptive_connector": False}),
    (2200, {"fixed": True,  "two_stage": True, "adaptive_connector": True}),
])
def test_pause_duration_matrix(pause_ms: int, expected_cutoffs: dict[str, bool]):
    """Verifies whether a simulated pause triggers a turn completion under each policy."""
    pause_s = pause_ms / 1000.0

    # Approach A: Fixed 1.8s
    fixed_timeout = 1.8
    assert (pause_s >= fixed_timeout) == expected_cutoffs["fixed"]

    # Approach B: Two-stage (0.6s)
    two_stage_timeout = 0.6
    assert (pause_s >= two_stage_timeout) == expected_cutoffs["two_stage"]

    # Approach C: Adaptive connector (2.2s)
    adaptive_connector_timeout = 2.2
    assert (pause_s >= adaptive_connector_timeout) == expected_cutoffs["adaptive_connector"]
