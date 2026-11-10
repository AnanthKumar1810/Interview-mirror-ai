# InterviewMirror AI — Phase 2: Why and how the evaluation engine works

## Goal

Move beyond fixed interview questions and a keyword-only score by adding:

1. **Auditable transcript-based scoring** across relevance (25), technical concept coverage (35), explanation clarity (20), and supporting detail (20).
2. **Verbatim evidence snippets** anchored in the candidate's submitted transcript.
3. **A transparent adaptive follow-up** that targets the weakest learning dimension.
4. **A three-question progression**: initial baseline question → curated adaptive follow-up → new baseline topic.
5. **A final dashboard**, with per-dimension averages and missing concepts to practice, plus JSON report.

### Important limitation

The numeric scores are **heuristic educational signals**, not a valid measure of technical factual accuracy, candidate competency, hiring suitability, pronunciation or accent. Recognizing a term such as *Docker*, *validation* or *precision* does not prove a statement is true. Measured results are quoted but **not verified**. The optional Ollama model provides qualitative comments only; it does not secretly adjust scores.

## Pipeline, with code references

```text
User records a short answer OR types one
                 |
      Frontend static/app.js
                 |
          POST /api/answer
                 |
         FastAPI main.py
                 |
     evaluation.py: evaluate_answer()
         |                     |
  rubric + excerpt        missing concepts
         |                     |
         +---------+-----------+
                   |
    adaptive.py: select_followup()
                   |
       Localized, curated prompt
                   |
      saved in Session.pending_question
                   |
         next_question returned
                   |
       static/app.js updates UI
                   |
           GET /api/report/id
                   |
       Summary dashboard + JSON
```

### 1. Why the rubric is transparent

`evaluation.py` groups specific expected concepts for each question by language and topic. For every concept group it records whether a phrase was detected and—only if there is a match—the **exact excerpt** from the candidate's input. It also identifies evidence hints such as personal actions, verification methods and quantitative results, and displays a limitation statement.

The four dimensions are scored with bounded, deterministic rules:

- **Relevance (25)** — breadth of expected concept mentions.
- **Technical concept coverage (35)** — whether key mechanisms are mentioned; **does not check truth**.
- **Clarity (20)** — rough transcript structure markers, length and explanations (not vocal fluency).
- **Supporting detail (20)** — mentions of actions, tests and quantification (claims unverified).

The score is the sum; each dimension is capped. These rules are stable and easy to test. They should **not** be confused with a validated automated interviewer; small synonym dictionaries will under-score valid paraphrases, especially in multilingual speech. A labeled calibration set is needed before showing these scores as reliable assessments.

### 2. Why question 2 is adaptive but question 3 is fixed

`adaptive.py` selects one of four **human-authored question templates**:

- Technical concepts missing? Ask for a concrete mechanism.
- Not enough supporting detail? Ask for tests, metrics or a failure example.
- Weak explanation structure? Ask for steps in order.
- Strong on the above? Ask for an architectural trade-off.

This prevents an unconstrained LLM from generating irrelevant or unsafe interview questions and ensures English/Telugu/Hindi prompts exist. Each adaptive prompt has its **own scoring criteria**. The third question tests another topic to avoid overfitting the entire session to one initial answer.

This is **rule-based adaptation**; it is not falsely presented as autonomous LLM reasoning. Later, an LLM can propose follow-ups with schema validation, repetition checks and safe fallback to these templates.

### 3. Why explanations quote the original answer

An educational tool must tell the candidate *which words led to feedback*. `evidence_items[].quote` is always sliced from the text the candidate submitted. The UI displays it with `textContent`, not unsafe HTML. The answer itself could contain false claims; these quotes are evidence of *what was said*, not independent verification.

### 4. Why the dashboard uses dimension averages

`GET /api/report/{session_id}` returns `dimension_averages`, `dimension_max`, `review_priorities`, and the three `results`. The frontend renders a local-only summary. JSON is downloadable for reproducible review; the session is still stored only in server memory.

### 5. How to verify

From the project folder:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8002
```

Open http://127.0.0.1:8002. Without a Gnani key, use **typed answers** or clearly labeled synthetic samples. With credentials, transcribe a short voice answer before submitting the transcript. The recommended quick smoke test:

1. Select Agentic AI / English → Start Interview.
2. Type a very short response like "I built an agent" → Get feedback.
3. Verify the score, expected-concept checklist, excerpt and explanation.
4. Click Next Question: it should now be a **technical adaptive follow-up**.
5. Answer it → Next Question: should move to a different core topic.
6. Finish and verify the summary and exported JSON.

## What remains for a rigorous public demo

- Test actual Gnani Prisma and Timbre requests with your own API key and microphone in a compatible browser.
- Calibrate scoring against human-rated multilingual answer examples; report agreement and failure patterns.
- Evaluate content quality beyond keyword matching with a carefully grounded reference or LLM review, with error analysis and transparency about uncertainty.
- Persist sessions in a database (currently local volatile memory); add consent and data retention controls before deployment.
- For answers longer than 30 seconds, use Gnani streaming or careful chunking, rather than sending oversized clips to REST STT.

**This is Phase 2 implemented on the separate v2 archive available in this conversation. It does not modify your other Windows checkout shown in screenshots (`app/`-based API under `/api/sessions/...`).**
