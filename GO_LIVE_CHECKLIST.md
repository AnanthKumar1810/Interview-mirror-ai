# InterviewMirror AI — Gnani Challenge Readiness Checklist

Do not mark a live capability complete unless evidence was observed with your own Gnani credentials.

## 1. Local server and audio (does not need Gnani)

- [ ] Start the app with `QUICKSTART_WINDOWS.ps1`; open http://127.0.0.1:8001.
- [ ] Visit http://127.0.0.1:8001/api/diagnostics and confirm the backend reports `ok`.
- [ ] Start an interview in **English** and record for 5–10 seconds.
- [ ] See `Local audio check` including duration and PCM WAV characteristics.
- [ ] Replay the clip and confirm the words are intelligible.
- [ ] Save the WAV to your computer for the independent Prisma test.
- [ ] Repeat the local audio test with **Telugu** speech.
- [ ] Complete a text-practice session (three questions) and download its JSON report.

## 2. Genuine Gnani smoke tests (requires valid key; may consume credits)

1. Set `GNANI_API_KEY=...` in your **local** `.env`; restart server.
2. The page must say `KEY LOADED (UNVERIFIED)` until an actual call succeeds.
3. In a second PowerShell terminal (from project root):

```powershell
.\.venv\Scripts\python.exe verify_live.py --tts --language en-IN --output english-question.wav
.\.venv\Scripts\python.exe verify_live.py --tts --language te-IN --output telugu-question.wav
.\.venv\Scripts\python.exe verify_live.py --audio candidate-english.wav --language en-IN
.\.venv\Scripts\python.exe verify_live.py --audio candidate-telugu.wav --language te-IN
```

- [ ] English question audio opens and sounds correct.
- [ ] Telugu question audio opens and sounds correct.
- [ ] English Prisma output matches actual recorded English speech reasonably well.
- [ ] Telugu Prisma output matches actual recorded Telugu speech reasonably well.
- [ ] End-to-end app path: listen → record → local WAV check → Gnani transcript → edit → feedback → next question.
- [ ] Repeat end-to-end in Telugu. Note any script/code-mixing problems for honest demo claims.

The candidate WAV files must be actual 16kHz 16-bit mono WAV files, lasting 0.2–30 seconds. You can use **Save WAV** from the browser after recording.

## 3. Honest final demo

- [ ] Show the actual Gnani-backed voice workflow—not a mock transcript labeled as STT.
- [ ] Demonstrate one realistic technical answer about AgentForge or another project.
- [ ] Show evidence excerpts and a missing-concept-driven follow-up.
- [ ] Show the result dashboard and explain that numeric scores are practice indicators, not proven factual correctness.
- [ ] Ensure the screen/video does not display `.env`, tokens, personal email addresses, or private interview recordings.
- [ ] Review current official submission instructions, including deadline and public demo requirements, before posting.
- [ ] Save the final source ZIP, a playable demo clip, and a short README describing setup and known limitations.

## Distinguish these statuses

- **Implemented:** code exists.
- **Offline tested:** fake responses/unit tests verify expected request/response behavior.
- **Live verified:** an actual provider call returned valid audio/transcript on the account intended for the demo.
- **Submitted:** official portal/post confirmation received.

As of this release, voice features are **implemented and offline tested, not live verified or submitted**.
