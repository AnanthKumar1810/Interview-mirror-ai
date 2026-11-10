"""Regression checks for merging the old session-style and newer API shapes."""
import io
import wave
import math
import struct
import httpx
from fastapi.testclient import TestClient

import main
from gnani import GnaniClient, STT_URL, TTS_URL

client = TestClient(main.app)


def make_wav():
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b''.join(struct.pack('<h', int(2000 * math.sin(2 * math.pi * 220 * i / 16000))) for i in range(16000)))
    return out.getvalue()


def test_unified_session_route_and_typed_fallback():
    data = client.post('/api/sessions', json={'track': 'agentic', 'language': 'te-IN'}).json()
    assert data['session_id'] and data['question'] == data['current_question']
    sid = data['session_id']
    first = client.post(f'/api/sessions/{sid}/answers', data={
        'mock_transcript': 'I built an agent with a Python tool and tested the output.'
    })
    assert first.status_code == 200, first.text
    assert first.json()['source'] == 'typed'
    assert first.json()['stt'] is None
    assert first.json()['next_question_kind'] == 'adaptive'
    after = client.get(f'/api/sessions/{sid}').json()
    assert after['answered'] == 1 and len(after['answers']) == 1
    assert after['current_question'] == first.json()['next_question']


def test_unified_session_voice_path_mocked_end_to_end(monkeypatch):
    seen = []
    def handler(request):
        seen.append((str(request.url), request.headers.get('X-API-Key-ID')))
        if str(request.url) == STT_URL:
            assert b'language_code' in request.content and b'en-IN' in request.content
            assert b'audio_file' in request.content
            return httpx.Response(200, json={
                'success': True, 'transcript': 'I tested my project with Python and Docker.',
                'model': 'prisma-v2.5', 'request_id': 'mock-req'
            })
        if str(request.url) == TTS_URL:
            assert b'Pranav' in request.content
            return httpx.Response(200, content=make_wav(), headers={'content-type': 'audio/wav'})
        return httpx.Response(404)
    gnani = GnaniClient(api_key='safe-dummy', client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(main, 'provider', lambda: gnani)
    sid = client.post('/api/sessions', json={'track': 'software', 'language': 'en-IN'}).json()['session_id']
    speech = client.get(f'/api/sessions/{sid}/question-audio')
    assert speech.status_code == 200 and speech.content[:4] == b'RIFF'
    recorded = client.post(f'/api/sessions/{sid}/answers', files={
        'audio': ('recording.wav', make_wav(), 'audio/wav')
    }, data={'consent':'true'})
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()['source'] == 'gnani_prisma'
    assert recorded.json()['stt']['request_id'] == 'mock-req'
    assert len(seen) == 2 and all(k == 'safe-dummy' for _, k in seen)


def test_placeholders_are_not_configured():
    assert not GnaniClient(api_key='your_actual_api_key_here').enabled
    assert not GnaniClient(api_key='<api-key>').enabled
    assert GnaniClient(api_key='a-realistic-looking-secret-value').enabled


def test_diagnostics_never_echo_key(monkeypatch):
    monkeypatch.setattr(main, 'provider', lambda: GnaniClient(api_key='SUPER-SECRET'))
    response = client.get('/api/diagnostics')
    assert response.status_code == 200
    body = response.json()
    assert body['gnani_key_configured'] is True
    assert body['gnani_live_verified'] is False
    assert 'SUPER-SECRET' not in response.text


def test_invalid_audio_and_no_key_do_not_create_answer(monkeypatch):
    monkeypatch.setattr(main, 'provider', lambda: GnaniClient(api_key=''))
    sid = client.post('/api/sessions', json={'track':'ai','language':'en-IN'}).json()['session_id']
    invalid = client.post(f'/api/sessions/{sid}/answers', files={
        'audio': ('bad.wav', b'not-wav', 'audio/wav')})
    assert invalid.status_code == 422
    missing_key = client.post(f'/api/sessions/{sid}/answers', files={
        'audio': ('recording.wav', make_wav(), 'audio/wav')}, data={'consent':'true'})
    assert missing_key.status_code == 503
    assert client.get(f'/api/sessions/{sid}').json()['answered'] == 0


def test_original_and_new_routes_unchanged():
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/status').status_code == 200
    assert client.get('/api/diagnostics').status_code == 200
    assert client.get('/api/docs').status_code == 200
