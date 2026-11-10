"""InterviewMirror AI — FastAPI with SQLite persistence and optional authenticated sessions."""
from __future__ import annotations

import os
import uuid
import time
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Depends
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from coach import QUESTION_BANK, TRACK_LABELS, evaluate, ollama_refine
from adaptive import select_followup
from gnani import GnaniClient, GnaniError
from audio_tools import ALLOWED_AUDIO_MIME, MAX_AUDIO_BYTES, inspect_pcm16_wav
from speech_enhancement import enhance_pcm16_wav
from robust_evaluation import evaluate_for_app
from storage import SQLiteStore, ConflictError
from auth_service import auth_required, principal, issue_token, parse_token, hash_password, verify_password, validate_deployment_config
import sqlite3

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
validate_deployment_config()
STORE = SQLiteStore(os.getenv("IM_DATABASE_PATH", str(ROOT / ".data" / "interviewmirror.sqlite3")))

def current_owner(request: Request) -> str | None:
    return principal(request, STORE)

app = FastAPI(title="InterviewMirror AI", version="0.1.0", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def basic_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response

SUPPORTED_LANGUAGES = {"en-IN": "English", "te-IN": "Telugu", "hi-IN": "Hindi"}
MAX_ANSWERS = 3
SESSION_TTL_SECONDS = min(max(int(os.getenv("IM_SESSION_TTL_SECONDS", "86400")), 60), 604800)
# Best-effort per-process safety budget. Production reverse proxies must enforce
# their own per-user limits and concurrency quotas; this is not user auth.
_PROVIDER_CALLS = deque()
_PROVIDER_RATE_LOCK = threading.Lock()


def _reserve_provider_call() -> None:
    limit = min(max(int(os.getenv("IM_PROVIDER_CALLS_PER_MINUTE", "60")), 1), 600)
    with _PROVIDER_RATE_LOCK:
        now = time.monotonic()
        while _PROVIDER_CALLS and _PROVIDER_CALLS[0] <= now - 60:
            _PROVIDER_CALLS.popleft()
        if len(_PROVIDER_CALLS) >= limit:
            raise HTTPException(429, "Speech provider call budget exceeded. Try again later.")
        _PROVIDER_CALLS.append(now)


@dataclass
class Session:
    track: str
    language: str
    question_index: int = 0
    answers: list = field(default_factory=list)
    pending_question: dict | None = None
    pending_kind: str = "core"
    pending_reason: str = ""
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Best-effort per-process login throttle; proxy-level shared throttling is still
# mandatory for a production deployment with multiple replicas.
_AUTH_REQUESTS: dict[str, deque] = {}
_AUTH_LOCK = threading.Lock()


def _limit_auth(request: Request) -> None:
    ip = request.client.host if request.client else 'unknown'
    with _AUTH_LOCK:
        q = _AUTH_REQUESTS.setdefault(ip, deque())
        now = time.monotonic()
        while q and q[0] < now - 300:
            q.popleft()
        if len(q) >= 30:
            raise HTTPException(429, 'Too many authentication attempts')
        q.append(now)


class CredentialsRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)


def normalized_email(email: str) -> str:
    value = email.strip().lower()
    if value.count('@') != 1 or '.' not in value.split('@')[-1] or ' ' in value:
        raise HTTPException(422, 'Enter a valid email address')
    return value


@app.post('/api/auth/register', status_code=201)
def register(request: CredentialsRequest, http_request: Request):
    _limit_auth(http_request)
    email = normalized_email(request.email)
    # Fails closed if the operator did not configure a signing key.
    from auth_service import security_key
    security_key()
    try:
        user_id = STORE.create_user(email, hash_password(request.password))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'An account with that email already exists')
    return {'access_token': issue_token(user_id), 'token_type': 'bearer', 'expires_in': 3600}


@app.post('/api/auth/login')
def login(request: CredentialsRequest, http_request: Request):
    _limit_auth(http_request)
    from auth_service import security_key
    security_key()
    email = normalized_email(request.email)
    account = STORE.user_by_email(email)
    if not verify_password(request.password, account['password_hash'] if account else None):
        raise HTTPException(401, 'Incorrect email or password')
    return {'access_token': issue_token(account['id']), 'token_type': 'bearer', 'expires_in': 3600}


@app.get('/api/auth/me')
def me(user_id: str | None = Depends(current_owner)):
    if user_id is None:
        raise HTTPException(401, 'Authentication is disabled in local demo mode')
    return STORE.user_by_id(user_id)


@app.post('/api/auth/logout')
def logout(request: Request, user_id: str | None = Depends(current_owner)):
    if user_id is None:
        raise HTTPException(401, 'Not authenticated')
    token = request.headers.get('Authorization', '')[7:]
    claims = parse_token(token, STORE)
    STORE.revoke_token(claims['jti'], int(claims['exp']))
    return {'signed_out': True}


@app.delete('/api/auth/me')
def delete_account(user_id: str | None = Depends(current_owner)):
    if user_id is None:
        raise HTTPException(401, 'Not authenticated')
    STORE.delete_user(user_id)
    return {'deleted': True}


@app.get('/api/my/sessions')
def my_sessions(user_id: str | None = Depends(current_owner)):
    if user_id is None:
        raise HTTPException(401, 'Authentication required for account history')
    return {'sessions': STORE.recent_sessions(user_id)}


class StartRequest(BaseModel):
    track: str = "agentic"
    language: str = "en-IN"

class AnswerRequest(BaseModel):
    session_id: str
    text: str = Field(min_length=3, max_length=4000)

class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=650)
    language: str = "en-IN"


def get_session(session_id: str, owner_id: str | None = None) -> Session:
    # Ownership is enforced in SQL; different users receive the same 404 as a missing ID.
    record = STORE.get_session(session_id, owner_id)
    if record is None:
        raise HTTPException(404, "Unknown session, expired session, or inaccessible account data.")
    session = Session(**record['state'])
    session._version = record['version']
    return session


def persist_session(session_id: str, session: Session, owner_id: str | None):
    try:
        STORE.update_session(session_id, owner_id, asdict(session), session._version)
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


def current_question_spec(session: Session) -> dict | None:
    if session.question_index >= MAX_ANSWERS:
        return None
    if session.pending_question is not None:
        return session.pending_question
    return QUESTION_BANK[session.track][0]


def current_question(session: Session) -> str | None:
    q = current_question_spec(session)
    return q[session.language] if q else None


def provider() -> GnaniClient:
    return GnaniClient()


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/status")
def status():
    gnani_on = provider().enabled
    return {"gnani_live": gnani_on,
            "stt_model": "prisma-v2.5", "tts_model": "timbre-v2.5",
            "ollama_enabled": bool(os.getenv("OLLAMA_MODEL", "").strip()),
            "neural_enhancement_dependency_present": __import__("importlib.util", fromlist=["find_spec"]).find_spec("df") is not None,
            "tracks": TRACK_LABELS, "languages": SUPPORTED_LANGUAGES,
            "mode": "gnani_live" if gnani_on else "local_demo",
            "coach_version": "risk_aware_rubric_v3", "adaptive_followups": True, "provider_audio_consent_required": True,
            "auth_required": auth_required(), "storage": "sqlite_persistent",
            "verification": "key_configured_only_not_tested" if gnani_on else "key_missing"}


@app.get("/api/health")
def health():
    """Backward-compatible health route; a configured key is NOT proof of valid credentials."""
    is_configured = provider().enabled
    return {"status": "ok", "mode": "gnani_live" if is_configured else "mock",
            "provider_configured": is_configured,
            "stt_model": "prisma-v2.5", "tts_model": "timbre-v2.5"}


@app.post("/api/session")
def start_session(request: StartRequest, user_id: str | None = Depends(current_owner)):
    if request.track not in QUESTION_BANK or request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(422, "Unsupported track or language.")
    session_id = str(uuid.uuid4())
    session = Session(track=request.track, language=request.language)
    STORE.create_session(session_id, asdict(session), user_id, SESSION_TTL_SECONDS)
    return {"session_id": session_id, "question": current_question(session),
            "question_number": 1, "total_questions": MAX_ANSWERS,
            "track": request.track, "language": request.language,
            "question_kind": "core", "question_reason": ""}


@app.post("/api/answer")
def answer(request: AnswerRequest, user_id: str | None = Depends(current_owner)):
    session = get_session(request.session_id, user_id)
    if session.question_index >= MAX_ANSWERS:
        raise HTTPException(409, "Interview already complete. Start a new session.")
    text = request.text.strip()
    if len(text) < 3:
        raise HTTPException(422, "Answer is too short.")
    q = current_question_spec(session)
    qtext = q[session.language]
    # The follow-up has its own expected concepts; do not score it against the
    # original prompt's rubric. Numerical scores are practice indicators only.
    fixed_index = 0 if session.question_index == 0 else 1 if session.question_index == 2 else None
    feedback = evaluate_for_app(text, q, session.language, session.track, fixed_index)
    feedback = ollama_refine(text, qtext, feedback)
    session.answers.append({"question": qtext, "question_kind": session.pending_kind,
                            "question_reason": session.pending_reason,
                            "transcript": text, "feedback": feedback})
    session.question_index += 1
    done = session.question_index == MAX_ANSWERS
    if session.question_index == 1:
        question, reason, focus = select_followup(session.track, session.language, feedback)
        session.pending_question = question
        session.pending_kind = "adaptive"
        session.pending_reason = reason
        # In this three-question session the second question probes a specific
        # missing dimension. Third question restores subject breadth.
        feedback["follow_up"] = question[session.language]
        feedback["follow_up_focus"] = focus
    elif session.question_index == 2:
        session.pending_question = QUESTION_BANK[session.track][1]
        session.pending_kind = "core"
        session.pending_reason = "Returning to a separate topic for broader practice."
        feedback["follow_up"] = session.pending_question[session.language]
    else:
        session.pending_question = None
        session.pending_kind = "complete"
        session.pending_reason = ""
    persist_session(request.session_id, session, user_id)
    return {"transcript": text, "feedback": feedback, "completed": done,
            "answered": session.question_index, "total_questions": MAX_ANSWERS,
            "next_question": current_question(session),
            "next_question_kind": session.pending_kind if not done else None,
            "next_question_reason": session.pending_reason if not done else None,
            "average_score": round(sum(a["feedback"]["score"] for a in session.answers) / len(session.answers))}


@app.get("/api/report/{session_id}")
def report(session_id: str, user_id: str | None = Depends(current_owner)):
    session = get_session(session_id, user_id)
    scores = [item["feedback"]["score"] for item in session.answers]
    dimension_max = {"relevance": 25, "technical_coverage": 35, "clarity": 20, "evidence": 20}
    dimension_averages = {
        key: round(sum(a["feedback"]["dimensions"][key] for a in session.answers) / len(session.answers), 1)
        for key in dimension_max
    } if session.answers else {}
    missing = {}
    for answer_item in session.answers:
        for concept in answer_item["feedback"].get("missing_concepts", []):
            missing[concept] = missing.get(concept, 0) + 1
    priorities = [concept for concept, _ in sorted(missing.items(), key=lambda p: (-p[1], p[0]))][:5]
    return {"title": "InterviewMirror AI practice report", "session_id": session_id,
            "created": session.created, "track": TRACK_LABELS[session.track],
            "language": SUPPORTED_LANGUAGES[session.language],
            "answered": len(session.answers), "total_questions": MAX_ANSWERS,
            "average_score": round(sum(scores) / len(scores)) if scores else None,
            "dimension_averages": dimension_averages, "dimension_max": dimension_max,
            "review_priorities": priorities,
            "results": session.answers,
            "method": "risk_aware_rubric_v3",
            "note": "Uncalibrated transcript-only coaching. Risk flags are heuristic or model-generated, not a validated technical correctness or hiring assessment."}


async def _verified_wav_upload(audio: UploadFile) -> tuple[bytes, dict]:
    """Validate format and size; never dispatch invalid audio to a paid provider."""
    if audio.content_type not in ALLOWED_AUDIO_MIME:
        raise HTTPException(415, "Submit a WAV file (16-bit mono, 16 kHz).")
    raw = await audio.read(MAX_AUDIO_BYTES + 1)
    await audio.close()
    if len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording too large. Record a shorter answer.")
    try:
        info = inspect_pcm16_wav(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return raw, info


@app.post("/api/audio/check")
async def audio_check(audio: UploadFile = File(...), user_id: str | None = Depends(current_owner)):
    """Free offline microphone/encoder diagnostic; does not store or upload to Gnani."""
    _, info = await _verified_wav_upload(audio)
    return info


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form("en-IN"),
                     enhancement: str = Form("off"), consent: bool = Form(False), track: str = Form(""),
                     user_id: str | None = Depends(current_owner)):
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(422, "Unsupported language.")
    if track and track not in QUESTION_BANK:
        raise HTTPException(422, "Unsupported interview focus.")
    raw, info = await _verified_wav_upload(audio)
    if info["possibly_silent"]:
        raise HTTPException(422, "Recording appears silent. Check microphone input and retry before using Gnani credits.")
    if not consent:
        raise HTTPException(422, "Explicit consent is required before forwarding audio to Gnani.")
    try:
        processed, noise_info = await run_in_threadpool(enhance_pcm16_wav, raw, mode=enhancement)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    _reserve_provider_call()
    try:
        terms = [term for question in QUESTION_BANK.get(track, []) for term in question.get("keywords", [])]
        response = await run_in_threadpool(provider().transcribe, processed, language, terms)
        # Do not expose recorded audio or secrets. Enhancement accuracy is unverified.
        return {**response, "audio_processing": noise_info}
    except GnaniError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/speak")
def speak(request: SpeakRequest, user_id: str | None = Depends(current_owner)):
    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(422, "Unsupported language.")
    _reserve_provider_call()
    try:
        data = provider().synthesize(request.text.strip(), request.language)
    except GnaniError as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(content=data, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# Compatibility adapters for the known session-oriented Windows API routes.
# They use the very same Session objects, evaluator and Gnani client as the
# consolidated frontend. This is NOT a drop-in claim for the unavailable UI.
@app.post("/api/sessions")
def create_session_compat(request: StartRequest, user_id: str | None = Depends(current_owner)):
    data = start_session(request, user_id)
    return {**data, "current_question": data["question"], "answered": 0,
            "mode": "live" if provider().enabled else "mock"}


@app.get("/api/sessions/{session_id}")
def get_session_compat(session_id: str, user_id: str | None = Depends(current_owner)):
    session = get_session(session_id, user_id)
    return {
        "session_id": session_id, "track": session.track, "language": session.language,
        "current_question": current_question(session),
        "question_number": min(session.question_index + 1, MAX_ANSWERS),
        "answered": len(session.answers), "completed": session.question_index >= MAX_ANSWERS,
        "answers": session.answers,
    }


@app.get("/api/sessions/{session_id}/question-audio")
def question_audio_compat(session_id: str, user_id: str | None = Depends(current_owner)):
    session = get_session(session_id, user_id)
    question = current_question(session)
    if question is None:
        raise HTTPException(409, "Interview already completed.")
    return speak(SpeakRequest(text=question, language=session.language), user_id)


@app.post("/api/sessions/{session_id}/answers")
async def submit_answer_compat(
    session_id: str,
    audio: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    mock_transcript: str | None = Form(None),
    enhancement: str = Form("off"),
    consent: bool = Form(False),
    user_id: str | None = Depends(current_owner),
):
    session = get_session(session_id, user_id)
    text = (transcript or mock_transcript or "").strip()
    source = "typed" if text else "gnani_prisma"
    stt_metadata = None
    if not text:
        if audio is None:
            raise HTTPException(422, "Provide a transcript or a 16 kHz mono WAV recording.")
        stt_metadata = await transcribe(audio, session.language, enhancement, consent, user_id)
        text = stt_metadata["transcript"]
    # The UI's mock transcript field never masquerades as an STT response.
    result = answer(AnswerRequest(session_id=session_id, text=text), user_id)
    return {**result, "source": source, "stt": stt_metadata}


@app.get("/api/diagnostics")
def diagnostics(user_id: str | None = Depends(current_owner)):
    """Safe configuration snapshot; deliberately never echoes credentials."""
    configured = provider().enabled
    return {
        "backend": "ok", "gnani_key_configured": configured,
        "gnani_live_verified": False,
        "verification_note": "This endpoint does not call Gnani. Use verify_live.py for a real API test.",
        "voice_requests_enabled": configured, "audio_consent_required": True,
        "stt": {"model": "prisma-v2.5", "endpoint": "https://api.vachana.ai/stt/v3",
                "input": "WAV mono PCM16 8000 or 16000 Hz, <=30 seconds"},
        "tts": {"model": "timbre-v2.5", "endpoint": "https://api.vachana.ai/api/v1/tts/inference",
                "response": "binary WAV"},
        "interfaces": ["/api/session", "/api/answer", "/api/audio/check", "/api/transcribe", "/api/speak",
                       "/api/report/{session_id}", "/api/sessions", "/api/sessions/{session_id}/answers"],
    }


@app.delete("/api/session/{session_id}")
@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, user_id: str | None = Depends(current_owner)):
    get_session(session_id, user_id)
    STORE.delete_session(session_id, user_id)
    return {"deleted": True, "session_id": session_id}

