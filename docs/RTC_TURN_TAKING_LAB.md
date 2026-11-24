# InterviewMirror RTC turn-taking lab

The optional LiveKit worker now tracks user/agent speech overlap. A brief
"hmm" or "okay" while the agent is speaking is ignored as a backchannel.
A short answer such as "No" remains a valid answer. Exact requests such
as "please repeat the question" replay the pending question without scoring it.
Substantive overlapping input interrupts the tracked LiveKit SpeechHandle.
If VAD already interrupted the question on a backchannel, playback restarts
from the beginning; seamless continuation is not claimed.

The worker records anonymous aggregate counts and callback-time p50/p95 under
`.data/rtc-turn-lab/` (configurable with `IM_RTC_TURN_METRICS_DIR`). It does
not save recordings, transcripts or session IDs. English/Hindi retain the
existing multilingual end-of-turn model; Telugu uses VAD endpointing.
Adaptive interruption stays opt-in because it requires LiveKit model service.

Run offline replay: `python -m eval_harness.rtc_turn_replay`.
The six synthetic scenarios cover backchannels, repeat requests, true
interruptions, short answers, qualified acknowledgments and empty transcripts.
The earlier local replay passed 6/6; its constructed callback intervals gave
p50 220 ms and p95 350 ms. These numbers do not measure actual audio.
Real false/missed interruption rates and end-to-end response latency require
labelled recordings, microphone playback, Gnani access and a LiveKit session.
The current environment cannot verify those live conditions.
