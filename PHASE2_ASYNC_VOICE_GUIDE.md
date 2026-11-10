# Phase 2 — Async Python, FastAPI, and real-time voice-agent readiness

**Target:** TheInterviews.ai AI Engineering Intern (Voice Agents & LLM Evaluation).

## 1. What we inspected in the existing application

- `main.py`: `POST /api/transcribe` is `async def` but offloads the **synchronous** `GnaniClient.transcribe` to `run_in_threadpool`. This is legitimate compatibility behavior, not native async HTTP.
- `POST /api/speak` uses a synchronous route and synchronous `GnaniClient.synthesize`, which FastAPI schedules on its worker pool.
- `POST /api/answer` scores with `coach.evaluate` and may call optional blocking `ollama_refine` (qualitative explanations only).
- The browser currently uses discrete requests. No persistent media stream, VAD-mediated turn detection, barge-in, or LiveKit room integration is implemented.

## 2. New work in this phase

| File | Purpose | Verified? |
|---|---|---|
| `gnani_async.py` | `httpx.AsyncClient` Gnani STT/TTS adapter; safe error messages and response validation | Offline HTTPX mock contract tests |
| `voice_pipeline.py` | Injectable async STT → scoring → TTS batch-turn runner, per-stage monotonic timing, timeouts | Offline tests |
| `run_voice_pipeline.py` | 20-session mocked concurrency benchmark or opt-in live WAV experiment | Offline demo executed |
| `tests/test_async_voice.py` | Provider contract, timeout, fail-fast, concurrency and latency-percentile tests | Tests passed |

**Important:** These modules are *not wired into the existing UI* by default. This protects the current application while we learn. Live Gnani calls, true speech streaming, and LiveKit integration have **not** been validated in this environment.

## 3. First principles: async Python

### Sequential dependency and concurrency are different

A single voice turn has data dependencies:

```text
User WAV
  │
  ▼
[STT / Prisma] -- transcript --> [scoring / InterviewMirror rubric]
                                            │
                                            ▼
                                     [TTS / Timbre]
                                            │
                                            ▼
                                       audio reply
```

The stages in one turn are sequential: the scorer needs a transcript, and the pipeline waits for TTS to finish before reporting a completed batch turn. Meanwhile, *multiple sessions can overlap* their network waits on a shared event loop. Do not call `asyncio.gather(STT(), scorer(), TTS())` for a single dependent turn.

**Event loop:** A scheduler that resumes coroutines after nonblocking waits; not a thread-per-request design.

**Coroutine:** An `async def` function that returns an awaitable when invoked.

**`await`:** A suspension point that allows other tasks to run while awaited I/O is pending.

**Blocking call:** `requests.post()`, `httpx.Client.post()`, `time.sleep()`, or a CPU-heavy operation run directly inside an `async def`. They block the event loop unless offloaded or rewritten.

**`asyncio.to_thread()`:** Runs a synchronous function in a worker thread without blocking the event loop. It does **not** make CPU-bound Python code faster in general; the Global Interpreter Lock and workload matter. Cancellation of the awaiting coroutine does **not** stop the underlying thread. Do not put irreversible mutations in a timed-out background thread.

### Example

```python
import asyncio

async def io_request(name: str):
    await asyncio.sleep(0.2)  # models nonblocking network I/O
    return name

async def run():
    values = await asyncio.gather(io_request("A"), io_request("B"))
    return values

print(asyncio.run(run()))
```

The two independent waits overlap. With synchronous `time.sleep`, they would serialize if invoked directly on the event loop. Use a semaphore to cap provider concurrency rather than starting unlimited paid calls.

## 4. Observability metrics

This phase records batch stage wall-clock durations with `time.perf_counter()`:

- `stt`: time waiting for a completed transcript from provider.
- `scoring`: time for the deterministic scoring function on a worker thread.
- `tts`: time waiting for **complete** generated audio.
- `total`: time from beginning of STT until full generated audio is available.

**Not measured:** endpointing delay, streaming STT transcript delay, LLM time to first token, TTS time to first byte, packet-to-speaker latency, interruptions, or actual cost. This batch-turn setup should never be described as a production low-latency LiveKit pipeline.

For distributions, report p50/p95 with call count, provider, input length and environment. Under heavy-tailed latency, averages hide slow calls. With 20 samples, p95 is only an approximate indicator; do not use it for high-confidence SLA claims.

## 5. Run offline verification

From the project root, using Python 3.13 (3.11 also configured in CI):

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python run_voice_pipeline.py --demo --calls 20
```

`--demo` does **not** use an API key or provider. It synthesizes asynchronous waits and returns per-stage p50, p95 and max for 20 concurrent calls. Those latencies are simulation measurements and cannot predict real provider behavior.

## 6. Opt-in live test with Gnani

1. Set `GNANI_API_KEY` in local `.env`. Never commit it or share it in a chat/log.
2. Prepare a **consented**, approximately 2–10 second WAV, mono PCM16, 16,000 Hz.
3. Run:

```powershell
python run_voice_pipeline.py --wav .\sample_en.wav --track agentic --language en-IN --save-audio .\sample_reply.wav
```

Do not specify `--show-transcript` if you do not want the content printed in your terminal. This command will make *real billable network requests* to Gnani (STT and TTS); it is not run by offline tests. Test once with a short known utterance, then gradually collect performance metrics across different devices and languages.

## 7. Failure handling

| Failure | Detection | Appropriate response |
|---|---|---|
| Wrong WAV format | `inspect_pcm16_wav()` | Reject locally before paid STT call |
| STT timeout | `asyncio.wait_for()` | Mark transcription unavailable; no scoring or TTS |
| Empty transcript | Transcript validation | Ask for clearer/longer answer; no fake content |
| Scorer exception | Structured exception type | Fail, withhold fabricated score |
| TTS timeout or malformed WAV | Timeout / format validation | Mark audio-generation failure (do not claim voice reply succeeded) |
| Too many concurrent users | Semaphore / queue and rate limiting (future integration) | Backpressure, bounded queue, clear retry guidance |

Never retry every external operation automatically. Provider calls may incur cost, and non-idempotent operations can repeat side effects.

## 8. LiveKit next phase — verified concepts, not implemented integration

Current official documentation: https://docs.livekit.io/agents/logic/sessions/ and https://docs.livekit.io/agents/logic/turns/ . LiveKit's `AgentSession` orchestrates speech input, STT, LLM, TTS, turn detection, and interruptions. With the current documented interface, a basic session has this shape:

```python
from livekit.agents import AgentSession, Agent, TurnHandlingOptions

session = AgentSession(
    stt=stt_plugin,
    llm=llm_plugin,
    tts=tts_plugin,
    turn_handling=TurnHandlingOptions(turn_detection="stt"),
)
await session.start(room=ctx.room, agent=Agent(instructions="Be a concise interviewer."))
```

The variables `stt_plugin`, `llm_plugin`, `tts_plugin`, and `ctx` are deliberately **placeholders** requiring a configured LiveKit worker and compatible streaming providers. This snippet is not executable as-is and is not proof that Gnani supports these interfaces. STT/TTS providers may need custom LiveKit adapters. Do not install or test LiveKit without its specific credentials and a working plugin setup.

The next integration gate will be: verified STT/TTS plugin compatibility, live room connection, scripted turn-taking/interruptions, traced timings, and a small audio regression test set. LiveKit session tracing distinguishes end-of-turn detection, LLM first-token time, and TTS first-byte time, which our current batch instrumentation cannot provide: https://docs.livekit.io/reference/agents/session-traces/ .

## 9. Interview assessment questions

1. **Why isn't `async def` sufficient?** Because synchronous network/CPU operations in the coroutine still block the event loop; use native async I/O or a thread pool for blocking libraries.
2. **Why not parallelize STT/scoring/TTS for one turn?** The stages have data dependencies. You can overlap *independent user turns*, not execute downstream work before required inputs exist.
3. **What happens if STT takes 30 seconds?** A bounded timeout should stop waiting and prevent downstream work. Track errors and provider latency. Cancellation and cost semantics depend on the provider.
4. **What does p95 latency measure?** The threshold at which roughly 95% of observed completed calls are at or below that value; always specify the measurement boundary and sample size.
5. **Why is a completed-audio metric different from TTFB?** The former measures all synthesis time and transport; TTFB is the first audio byte and matters for perceived responsiveness.
6. **What would LiveKit add?** Streaming media transport, turn management, interrupts/barge-in, model orchestration and native session traces; still requires tests and compatible provider adapters.

## Status after Phase 2A

- Existing Phase 1 scoring baseline intact.
- All original and new offline unit tests pass (59 total in the verified environment).
- Native async HTTP adapter and pipeline tested only with mocked upstream responses.
- Real Gnani latency, LiveKit performance, user-facing integration and human-reviewed scorer accuracy remain unverified.
