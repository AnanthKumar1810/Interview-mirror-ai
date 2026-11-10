"""Noise path: format, opt-in, resampling and safety checks (NOT speech WER)."""
import io
import wave
import numpy as np
import httpx
from fastapi.testclient import TestClient
import main
from speech_enhancement import enhance_pcm16_wav
from gnani import GnaniClient, STT_URL


def make_audio(rate=8000, duration=1.5):
    rng = np.random.default_rng(42)
    n = int(rate * duration)
    times = np.arange(n) / rate
    noise = rng.normal(0, 0.02, n)
    voice = 0.12 * np.sin(2 * np.pi * 210 * times)
    voice[:int(rate * 0.4)] = 0
    pcm = (np.clip(noise + voice, -1, 1) * 32767).astype('<i2')
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm.tobytes())
    return out.getvalue()


def pcm_info(wav):
    with wave.open(io.BytesIO(wav), 'rb') as r:
        return r.getframerate(),r.getnframes()/r.getframerate(),np.frombuffer(r.readframes(r.getnframes()),dtype='<i2')


def test_raw_and_spectral_modes_are_valid_and_deterministic():
    original = make_audio()
    raw, raw_meta = enhance_pcm16_wav(original, mode='off')
    clean, clean_meta = enhance_pcm16_wav(original, mode='spectral')
    assert raw_meta['original_sample_rate_hz'] == 8000
    assert clean_meta['enhancement_accuracy_verified'] is False
    assert clean_meta['warning']
    for output in (raw, clean):
        rate, duration, samples = pcm_info(output)
        assert rate == 16000
        assert abs(duration - 1.5) < 0.001
        assert np.all(np.isfinite(samples))
    assert clean != raw
    assert enhance_pcm16_wav(original, mode='spectral')[0] == clean


def test_spectral_noise_gate_attenuates_stationary_noise_in_synthetic_fixture():
    original = make_audio(rate=16000)
    raw, _ = enhance_pcm16_wav(original, mode='off')
    clean, _ = enhance_pcm16_wav(original, mode='spectral')
    _, _, a = pcm_info(raw)
    _, _, b = pcm_info(clean)
    # First 0.4 s contains only synthetic stationary noise.
    n = int(16000 * 0.35)
    assert np.sqrt(np.mean(b[1000:n].astype(float)**2)) < np.sqrt(np.mean(a[1000:n].astype(float)**2))


def test_corrupted_audio_and_unknown_modes_rejected():
    import pytest
    with pytest.raises(ValueError):
        enhance_pcm16_wav(b'broken', mode='off')
    with pytest.raises(ValueError):
        enhance_pcm16_wav(make_audio(), mode='invented')


def test_gnani_mock_receives_enhanced_audio_and_metadata(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        assert str(request.url) == STT_URL
        assert b'name="audio_file"' in request.content
        # RIFF bytes supplied inside the multipart body
        assert b'RIFF' in request.content
        return httpx.Response(200, json={'success':True, 'transcript':'I built a system.', 'request_id':'mock'})
    gnani = GnaniClient(api_key='mock-key', client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(main, 'provider', lambda: gnani)
    client = TestClient(main.app)
    audio = make_audio(rate=8000)
    response = client.post('/api/transcribe', files={'audio': ('voice.wav', audio, 'audio/wav')},
                           data={'language': 'te-IN', 'enhancement': 'spectral', 'consent':'true'})
    assert response.status_code == 200, response.text
    assert response.json()['audio_processing']['enhancement'] == 'spectral'
    assert response.json()['audio_processing']['provider_sample_rate_hz'] == 16000
    assert len(calls) == 1
    rejected = client.post('/api/transcribe', files={'audio':('voice.wav',audio,'audio/wav')},
                           data={'language':'te-IN','enhancement':'unknown','consent':'true'})
    assert rejected.status_code == 422
    assert len(calls) == 1


def test_optional_neural_path_fails_explicitly_when_dependency_missing(monkeypatch):
    import speech_enhancement
    monkeypatch.setattr(speech_enhancement, '_deepfilter_model', lambda: (_ for _ in ()).throw(ValueError('Neural model unavailable')))
    import pytest
    with pytest.raises(ValueError, match='unavailable'):
        enhance_pcm16_wav(make_audio(), mode='deepfilter3')
