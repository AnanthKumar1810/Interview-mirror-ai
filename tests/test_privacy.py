import main
from fastapi.testclient import TestClient
from tests.test_api import wav_bytes
import httpx
from gnani import GnaniClient, STT_URL

client = TestClient(main.app)


def test_consent_is_required_before_external_provider_calls(monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'success':True,'transcript':'test'})
    gnani = GnaniClient(api_key='test', client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(main, 'provider', lambda: gnani)
    response = client.post('/api/transcribe', files={'audio': ('voice.wav', wav_bytes(), 'audio/wav')},
                           data={'language':'en-IN', 'enhancement':'off'})
    assert response.status_code == 422
    assert 'consent' in response.json()['detail'].lower()
    assert not seen
    allowed = client.post('/api/transcribe', files={'audio': ('voice.wav', wav_bytes(), 'audio/wav')},
                          data={'language':'en-IN', 'enhancement':'off','consent':'true'})
    assert allowed.status_code == 200
    assert len(seen) == 1


def test_session_delete_erases_answer_and_report_routes():
    response = client.post('/api/session', json={'track':'ai','language':'en-IN'}).json()
    sid = response['session_id']
    assert client.post('/api/answer', json={'session_id':sid, 'text':'I trained a model on a dataset.'}).status_code == 200
    assert client.delete(f'/api/session/{sid}').json()['deleted']
    assert client.get(f'/api/report/{sid}').status_code == 404
    assert client.get(f'/api/sessions/{sid}').status_code == 404


def test_response_security_headers():
    response = client.get('/api/health')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Cache-Control'] == 'no-store'
