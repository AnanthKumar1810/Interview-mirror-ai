"""Objective offline audio signal tests, never used as a surrogate for ASR WER."""
import json
import numpy as np
import pytest
from eval_harness.noise_quality import write_wav, measure_pair, run_manifest, snr_db, si_sdr_db


def test_noise_metrics_on_aligned_reference():
    clean = np.array([0.0, 0.1, -0.1, 0.2, -0.2, 0.0]) * 0.8
    assert snr_db(clean, clean) > 80
    assert si_sdr_db(clean, clean) > 60
    assert snr_db(clean, clean + .05) < snr_db(clean, clean)


@pytest.mark.parametrize('rate', [8000, 16000])
def test_noise_tool_keeps_valid_audio_and_finite_metrics(tmp_path, rate):
    rng = np.random.default_rng(11)
    t = np.arange(int(rate*1.5)) / rate
    clean = np.sin(2*np.pi*180*t)*.20
    clean[:rate//4] = 0
    noisy = clean + rng.normal(0,.04,len(clean))
    clean_path, noisy_path = tmp_path/'clean.wav', tmp_path/'noisy.wav'
    write_wav(clean_path, clean, rate)
    write_wav(noisy_path, noisy, rate)
    result = measure_pair(clean_path, noisy_path)
    assert result['modes']['off']['output_sample_rate_hz'] == 16000
    assert result['modes']['spectral']['processing_ms'] >= 0
    assert abs(result['modes']['spectral']['output_duration_seconds'] - 1.5) < .01
    assert np.isfinite(result['spectral_minus_raw']['snr_delta_db'])
    manifest = {'source':'synthetic', 'cases':[{'id':'test', 'clean':'clean.wav','noisy':'noisy.wav'}]}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    report = run_manifest(tmp_path/'manifest.json')
    assert report['asr_provider_calls'] == 0
    assert report['n_clips'] == 1
    assert 'ASR' not in ' '.join(report['aggregate'])


def test_manifest_path_traversal_is_blocked(tmp_path):
    manifest={'cases':[{'id':'unsafe','clean':'../outside.wav','noisy':'../outside.wav'}]}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='traversal'):
        run_manifest(tmp_path/'manifest.json')
