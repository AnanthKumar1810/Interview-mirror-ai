# Local native KV caching (experimental)

InterviewMirror can optionally use a dedicated llama.cpp server to select a
short localized conversational acknowledgment before its existing deterministic
next question. Scoring, question selection, STT and TTS are unchanged.
This is real model KV prefix reuse, not caching generated answers in Python.

## Setup (local development only)

Download a CUDA-enabled llama-server build and a compatible instruction-tuned
GGUF model (e.g. a small Qwen2.5 Instruct GGUF). Start one dedicated server:

    llama-server -m path/to/model.gguf --host 127.0.0.1 --port 8089 -ngl 99 -c 8192 --parallel 1 --slots --cache-ram 0 --no-cache-idle-slots --ctx-checkpoints 0

Use a recent llama.cpp build supporting these flags and native /completion
timings.cache_n. Do not expose the server to the network or other applications.
Avoid verbose prompt logging and do not configure any slot-save directory.
The host RAM prompt cache and context checkpoints must be disabled to avoid
retaining prior candidates' prompt states after slot erasure. For an 8 GB GPU,
start with a 3B model; adjust context and GPU offload to available VRAM.
Optional llama.cpp cache quantization flags (-ctk q8_0 -ctv q8_0) may reduce
VRAM on compatible builds; verify model and kernel support before use.

In the native backend's .env, set:

    IM_KV_CACHE_URL=http://127.0.0.1:8089

Restart FastAPI using one worker. This feature is off by default and disabled
in production. For development Docker Desktop, use the host.docker.internal URL
only if the host server is reachable over a protected private interface; do not
expose the inference server publicly. Native local backend is recommended.

## Behavior

- Stable instructions and bounded ordered question-answer history are sent to
  /completion with cache_prompt=true and id_slot=0. llama.cpp stores and
  reuses matching K/V tensors. Its native cache_n/prompt_n counters are used;
  missing metrics are null, never estimated hits.
- One slot is leased to an owner/session pair; switching sessions, a stale
  lease (>300 seconds on next access), or cold mode requires confirmed erasure
  before transmitting a prompt. No cross-candidate reuse. Completion,
  websocket teardown, deletion and correction release the active lease.
  Erasure is logical cache invalidation, not a secure memory wipe; on a failed
  erase the server may retain state until restarted. No disk cache is used.
- Concurrent requests fall back rather than queue. HTTP errors, invalid
  output, absent provider configuration and contention retain the deterministic
  bridge. The model selects only one allowlisted acknowledgment label, so
  free-form model output cannot become the spoken question or influence scores.
- The REST feedback carries kv_cache metrics; WebSocket events record timing
  and token counters without candidate text in the cache telemetry. Candidate
  transcripts are still handled by the existing app's consent/storage model.
- This is a single-worker, single-slot local prototype, not multi-tenant
  production infrastructure. Do not share the inference server with other apps.

## Test and measure

    python -m pytest -q tests/test_kv_cache.py
    python -m kv_cache --repeats 5

For the benchmark, stop active interview sessions and run against the dedicated
server with IM_KV_CACHE_URL set in the shell. Each synthetic cold request
erases the slot and disables prompt reuse; the matching warm request enables
reuse. Inspect native cached_tokens, prompt_tokens_evaluated, prefill_ms and
request_ms. A warm cache should report a positive cache_n and fewer evaluated
tokens on a compatible server. Request time is not TTFT or end-to-end speech
latency. Mock tests verify routing, isolation, fallback and telemetry, not GPU
execution. Live cache performance must be measured on target hardware before
claiming a speedup.

Upstream: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
