"""Submission-readiness checks: local audio validation must not contact Gnani."""
from __future__ import annotations
import io
import math
import struct
import wave
from fastapi.testclient import TestClient
import main
from gnani import GnaniClient

client = TestClient(main.app)


def wav_tone(volume: float = 0.12, seconds: int = 1) -> bytes:
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b''.join(struct.pack('<h', int(volume * 32767 * math.sin(2 * math.pi * 180 * i / 16000)))
                                for i in range(16000 * seconds)))
    return out.getvalue()


def test_offline_audio_check_works_without_api_key(monkeypatch):
    monkeypatch.setattr(main, 'provider', lambda: GnaniClient(api_key=''))
    response = client.post('/api/audio/check', files={'audio': ('recording.wav', wav_tone(), 'audio/wav')})
    assert response.status_code == 200
    data = response.json()
    assert data['format_valid'] is True
    assert data['sample_rate_hz'] == 16000
    assert data['channels'] == 1
    assert data['duration_seconds'] == 1.0
    assert not data['possibly_silent']
    assert data['rms_dbfs'] is not None
    assert 'transcript' not in data


def test_silent_mic_warning_and_no_paid_transcription(monkeypatch):
    monkeypatch.setattr(main, 'provider', lambda: GnaniClient(api_key='demo-not-real'))
    quiet = wav_tone(volume=0)
    response = client.post('/api/audio/check', files={'audio': ('test.wav', quiet, 'audio/wav')})
    assert response.status_code == 200
    assert response.json()['possibly_silent'] is True
    transcribed = client.post('/api/transcribe', files={'audio': ('test.wav', quiet, 'audio/wav')}, data={'language':'en-IN', 'consent':'true'})
    assert transcribed.status_code == 422
    assert 'silent' in transcribed.json()['detail']


def test_offline_check_rejects_invalid_encoding_or_media():
    assert client.post('/api/audio/check', files={'audio': ('test.webm', b'raw', 'audio/webm')}).status_code == 415
    assert client.post('/api/audio/check', files={'audio': ('bad.wav', b'not-a-wav', 'audio/wav')}).status_code == 422


def test_frontend_has_replay_export_and_transparency():
    res = client.get('/')
    assert res.status_code == 200
    assert 'id="preview-btn"' in res.text
    assert 'id="save-record-btn"' in res.text
    assert 'real transcription needs api access' in res.text.lower()
    js = client.get('/static/app.js').text
    assert "api('/api/audio/check'" in js
    assert "state.live" in js
    assert 'No Gnani key' in js
