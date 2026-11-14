import io
import wave
import math
import struct
import httpx
import pytest
from fastapi.testclient import TestClient

import main
from gnani import GnaniClient, GnaniError, STT_URL, TTS_URL

client = TestClient(main.app)


def wav_bytes(rate=16000, duration=1.0):
    output = io.BytesIO()
    with wave.open(output, 'wb') as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        frames = round(rate * duration)
        file.writeframes(b''.join(struct.pack('<h', int(2000 * math.sin(2 * math.pi * 220 * i / rate))) for i in range(frames)))
    return output.getvalue()


def test_website_and_demo_status(monkeypatch):
    monkeypatch.delenv('GNANI_API_KEY', raising=False)
    homepage = client.get('/')
    assert homepage.status_code == 200 and 'interviewmirror' in homepage.text.lower()
    info = client.get('/api/status').json()
    assert info['mode'] == 'local_demo' and info['stt_model'] == 'prisma-v2.5'
    health = client.get('/api/health').json()
    assert health['status'] == 'ok' and health['provider_configured'] is False


def test_full_three_question_interview():
    session = client.post('/api/session', json={'track': 'agentic', 'language': 'te-IN'})
    assert session.status_code == 200
    data = session.json()
    assert 'ఏజెంట్' in data['question']
    sid = data['session_id']
    for i in range(3):
        answer = client.post('/api/answer', json={
            'session_id': sid,
            'text': 'I built an agent with Python tools. First I wrote tests, then tested my fix and recorded the result.'
        })
        assert answer.status_code == 200
        body = answer.json()
        assert body['answered'] == i + 1
        assert (body['next_question'] is None) == (i == 2)
        assert body['feedback']['method'] == 'risk_aware_rubric_v3'
        assert 0 <= body['feedback']['score'] <= 100
    report = client.get(f'/api/report/{sid}').json()
    assert report['answered'] == 3
    assert len(report['results']) == 3
    assert report['average_score'] is not None
    assert client.post('/api/answer', json={'session_id': sid, 'text': 'more feedback'}).status_code == 409


def test_personalized_interview_with_achievements_evaluation():
    resume = (
        "B.Tech Computer Science graduate.\n"
        "Winner of National Hackathon 2024 with 1st prize.\n"
        "Built bug-fixer: automated SWE-bench repair in Python.\n"
        "Optimized repair pipeline latency by 50 percent across 100 benchmark tasks.\n"
    )
    session = client.post('/api/session', json={
        'track': 'agentic',
        'language': 'en-IN',
        'resume_text': resume,
        'github_repo': 'AnanthKumar1810/bug-fixer'
    })
    assert session.status_code == 200
    data = session.json()
    sid = data['session_id']
    # Q1: Introduction
    assert data['question_kind'] == 'introduction'
    assert 'introduce' in data['question'].lower()

    # Answer Q1
    ans1 = client.post('/api/answer', json={
        'session_id': sid,
        'text': 'Hello, I am a computer science graduate passionate about building autonomous software engineering agents.'
    }).json()
    assert ans1['answered'] == 1
    # Q2: Tailored project
    assert ans1['next_question_kind'] == 'personalized_project'
    assert 'bug-fixer' in ans1['next_question'] or 'Python' in ans1['next_question']

    # Answer Q2
    ans2 = client.post('/api/answer', json={
        'session_id': sid,
        'text': 'In bug-fixer, I developed a Python tool agent that reproduces bugs using Docker containers with approval guardrails.'
    }).json()
    assert ans2['answered'] == 2
    # Q3: Personalized achievement deep-dive
    assert ans2['next_question_kind'] == 'personalized_achievement'
    assert 'Hackathon' in ans2['next_question'] or 'Winner' in ans2['next_question'] or 'milestone' in ans2['next_question']

    # Answer Q3
    ans3 = client.post('/api/answer', json={
        'session_id': sid,
        'text': 'Our technical decision for the hackathon was an AST patch filter. We parallelized tests, which reduced latency by 50 percent and won 1st prize.'
    }).json()
    assert ans3['answered'] == 3
    assert ans3['completed'] is True

    # Report evaluation includes candidate profile and achievements
    rep = client.get(f'/api/report/{sid}').json()
    assert rep['answered'] == 3
    assert len(rep['achievements_evaluated']) >= 1
    assert any('Hackathon' in a or 'Winner' in a for a in rep['achievements_evaluated'])
    assert 'bug-fixer' in rep['github_repository_evaluated'] or 'Python' in rep['github_repository_evaluated']


def test_invalid_inputs_and_unknown_session():
    assert client.post('/api/session', json={'track': 'other', 'language': 'en-IN'}).status_code == 422
    assert client.post('/api/session', json={'track': 'ai', 'language': 'xx'}).status_code == 422
    assert client.get('/api/report/does-not-exist').status_code == 404
    assert client.post('/api/answer', json={'session_id': 'absent', 'text': 'hello'}).status_code == 404
    assert client.post('/api/speak', json={'text': 'test', 'language': 'unknown'}).status_code == 422


def test_demo_mode_does_not_fake_speech(monkeypatch):
    monkeypatch.delenv('GNANI_API_KEY', raising=False)
    audio = wav_bytes()
    response = client.post('/api/transcribe', files={'audio': ('voice.wav', audio, 'audio/wav')}, data={'language': 'en-IN', 'consent':'true'})
    assert response.status_code == 503 and 'key is missing' in response.json()['detail']
    response = client.post('/api/speak', json={'text': 'hello', 'language': 'en-IN'})
    assert response.status_code == 503


def test_reject_invalid_audio():
    wrong = client.post('/api/transcribe', files={'audio': ('voice.wav', wav_bytes(rate=11025), 'audio/wav')}, data={'language': 'en-IN', 'consent':'true'})
    assert wrong.status_code == 422
    too_long = client.post('/api/transcribe', files={'audio': ('voice.wav', wav_bytes(duration=31), 'audio/wav')}, data={'language': 'en-IN', 'consent':'true'})
    assert too_long.status_code == 422
    wrong_type = client.post('/api/transcribe', files={'audio': ('voice.webm', b'abcd', 'audio/webm')}, data={'language': 'en-IN', 'consent':'true'})
    assert wrong_type.status_code == 415


def test_real_gnani_request_contract_with_mock_transport():
    seen = []
    def handler(request):
        seen.append(request)
        assert request.headers['X-API-Key-ID'] == 'test-only'
        if str(request.url) == STT_URL:
            raw = request.content
            assert b'name="audio_file"' in raw
            assert b'name="language_code"' in raw and b'te-IN' in raw
            assert b'name="format"' in raw and b'transcribe' in raw
            assert b'name="model"' not in raw
            return httpx.Response(200, json={'success': True, 'transcript': 'నా ప్రాజెక్ట్', 'model': 'prisma-v2.5'})
        if str(request.url) == TTS_URL:
            content = request.content.decode('utf-8')
            assert 'Suhana' in content and 'timbre-v2.5' in content and 'te-IN' in content
            return httpx.Response(200, content=wav_bytes(), headers={'content-type': 'audio/wav'})
        return httpx.Response(404)
    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    gnani = GnaniClient(api_key='test-only', client=client_mock)
    assert gnani.transcribe(wav_bytes(), 'te-IN')['transcript'] == 'నా ప్రాజెక్ట్'
    assert gnani.synthesize('హలో', 'te-IN').startswith(b'RIFF')
    assert len(seen) == 2


def test_upstream_failure_propagates_without_secrets():
    def reject(request):
        return httpx.Response(401, json={'error': 'secret should not appear here'})
    gnani = GnaniClient(api_key='test-only', client=httpx.Client(transport=httpx.MockTransport(reject)))
    with pytest.raises(GnaniError, match='key is invalid') as exc:
        gnani.transcribe(wav_bytes(), 'en-IN')
    assert 'secret' not in str(exc.value)


def test_rest_routes_perform_end_to_end_with_mocked_provider(monkeypatch):
    """Validate browser->FastAPI->Gnani adapter with no external API traffic."""
    calls = []
    def respond(request):
        calls.append(request)
        if str(request.url) == STT_URL:
            assert b'language_code' in request.content
            return httpx.Response(200, json={"success": True, "transcript": "I built AgentForge.", "model": "prisma-v2.5"})
        if str(request.url) == TTS_URL:
            assert b'"model":"timbre-v2.5"' in request.content
            return httpx.Response(200, content=wav_bytes())
        return httpx.Response(404)
    gnani = GnaniClient(api_key='fake-key', client=httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(main, 'provider', lambda: gnani)
    stt = client.post('/api/transcribe', files={'audio': ('audio.wav', wav_bytes(), 'audio/wav')}, data={'language': 'en-IN', 'consent':'true'})
    assert stt.status_code == 200, stt.text
    assert stt.json()['transcript'] == 'I built AgentForge.'
    tts = client.post('/api/speak', json={'text': 'Tell me about your project.', 'language': 'en-IN'})
    assert tts.status_code == 200, tts.text
    assert tts.headers['content-type'] == 'audio/wav'
    assert tts.content[0:4] == b'RIFF'
    assert len(calls) == 2


def test_transcriber_rejects_empty_result():
    def respond(request):
        return httpx.Response(200, json={'success': True, 'transcript': '  '})
    gnani = GnaniClient(api_key='fake-key', client=httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(GnaniError, match='No speech detected'):
        gnani.transcribe(wav_bytes(), 'en-IN')


def test_tts_rejects_invalid_audio():
    def respond(request):
        return httpx.Response(200, content=b'RIFF' + b'\x00' * 100)
    gnani = GnaniClient(api_key='fake-key', client=httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(GnaniError, match='valid WAV'):
        gnani.synthesize('Hello!', 'en-IN')
