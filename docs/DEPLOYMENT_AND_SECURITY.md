# Deployment, privacy and production-readiness checklist

**Status: authenticated, SQLite-backed challenge prototype, NOT independently certified production ready.**

## Verified locally
- FastAPI starts; routes exercised using TestClient.
- 8/16 kHz mono PCM16 accepted, resampled to provider-compatible 16 kHz.
- Audio silence, invalid content types, long/corrupt recordings and missing consent rejected.
- Optional raw / spectral / DeepFilterNet3 processing modes; only spectral has deterministic unit tests.
- Transcript-level practice scoring includes explainable risk flags, optional strict-quote Ollama signal, and existing curated adaptive follow-up.
- Python test suite and CI drift/behavior gates; `Dockerfile` builds a non-root container when installed dependencies are available (image build not verified in this environment).
- HTTP response headers include `nosniff`, `no-referrer`, `DENY` frame policy and `no-store` for API routes.
- SQLite sessions have a configurable TTL and DELETE endpoint. Session ownership is authenticated when IM_AUTH_REQUIRED=true; tested across simulated restart.
- Provider requests have a best-effort per-process ceiling.

## Blocking issues for public / multi-tenant production
1. **Authentication & authorization** — local Argon2 + JWT accounts and SQL-level session ownership now implemented and unit-tested. Production still requires verified email, MFA/OIDC policy, distributed rate-limiting, session protections and threat review.
2. **Durable persistence** — SQLite WAL persists sessions across restarts with schema versioning, conflict detection and cleanup CLI. Managed Postgres, encrypted backups, tenant quotas, schema evolution tooling and retention scheduling remain for scaled production.
3. **End-user privacy** — consent records, vendor DPA, retention/deletion, data-subject access, encrypted storage, secrets manager and audit logging without transcripts.
4. **Operational controls** — TLS termination, strict CORS/CSP, rate limits via shared Redis/proxy, circuit breakers, quotas, retries with idempotency and per-tenant billing.
5. **Quality** — 20–50+ independently reviewed examples, real English/Telugu STT/TTS tests, live noisy WER comparison, scoring calibration, load tests, latency SLOs and external security assessment.
6. **Safety** — model and transcript prompt-injection threat modeling, evaluated uncertainty/abstention, failure recovery and candidate dispute/correction workflow.

## Local installation (Windows PowerShell)
```powershell
py -3.13 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\\.venv\\Scripts\\python.exe -m pytest -q
.\\.venv\\Scripts\\python.exe -m eval_harness.compare_robust
.\\.venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```
Open `http://127.0.0.1:8001`. When configured, use the **consent checkbox** before any external STT request. Choose raw mode initially and compare against enhancement before choosing a default.

## Local Docker
```bash
docker build -t interviewmirror-gnani:local .
docker run --rm --env-file .env -v interviewmirror_data:/app/.data -p 127.0.0.1:8001:8001 interviewmirror-gnani:local
```
Do not publish the demo directly to the internet without resolving the blockers above.

## Optional noise model
The bundled spectral gate works with NumPy/SciPy and has offline tests. To experiment with pretrained DeepFilterNet3, install a compatible Torch build and `pip install -r requirements-neural.txt`. DeepFilterNet3 is a 48-kHz speech enhancer; 8-kHz telephony must be upsampled, and it may reduce recognition accuracy. The neural path, model download, performance and Python 3.13 compatibility have **not** been tested in this environment.

## Real Gnani audio benchmark
Create a JSON manifest **outside this repository** containing consented WAV file paths, independent reference transcripts, language codes and IDs:
```json
{
  "cases": [
    {"id":"sample-001", "path":"clips/example.wav", "language":"te-IN",
     "reference_transcript":"Example transcript reviewed independently", "consent_for_provider":true}
  ]
}
```
Then run `python -m eval_harness.asr_ab --manifest /path/to/manifest.json --run-live --output reports/asr_ab_live.json`. The command makes **two real paid Prisma requests per clip**. Never include confidential recordings or unconsented voice data in a public demo or repo.
