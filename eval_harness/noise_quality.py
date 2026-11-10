"""Independent, *offline* noise-enhancement signal-quality benchmark.

Uses consented, paired clean/noisy WAVs (or explicitly synthetic espeak test
fixtures). Compares the exact same speech sample before and after enhancement.
Reports SNR, scale-invariant SDR, noise-only suppression, distortion and CPU
runtime. ASR WER and intelligibility require separate evaluation and are never
inferred from these metrics.

Run:
 python -m eval_harness.noise_quality --make-synthetic-fixtures path --output path/report.json
 python -m eval_harness.noise_quality --manifest path/manifest.json --output path/report.json
"""
from __future__ import annotations

import argparse
import io
import json
import math
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from speech_enhancement import enhance_pcm16_wav


def read_mono_pcm16(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), 'rb') as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != 'NONE':
            raise ValueError(f'{path.name} must be mono uncompressed PCM16 WAV')
        rate = wav.getframerate()
        data = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float64) / 32768.0
    if rate not in (8000, 16000):
        raise ValueError('This benchmark requires 8 kHz or 16 kHz aligned audio')
    return data, rate


def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((np.clip(samples, -1, .999969) * 32768).astype('<i2').tobytes())


def decode_wav_bytes(raw: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(raw), 'rb') as wav:
        data = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float64) / 32768
        return data, wav.getframerate()


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x) + 1e-14))


def snr_db(clean: np.ndarray, estimate: np.ndarray) -> float:
    if len(clean) != len(estimate):
        raise ValueError('Reference and estimate sample lengths differ')
    return round(20 * math.log10((rms(clean) + 1e-12) / (rms(estimate - clean) + 1e-12)), 3)


def si_sdr_db(clean: np.ndarray, estimate: np.ndarray) -> float:
    centered_ref, centered_est = clean - clean.mean(), estimate - estimate.mean()
    target = (np.dot(centered_est, centered_ref) / (np.dot(centered_ref, centered_ref) + 1e-12)) * centered_ref
    residual = centered_est - target
    return round(10 * math.log10((np.dot(target, target) + 1e-12) / (np.dot(residual, residual) + 1e-12)), 3)


def measure_pair(clean_path: Path, noisy_path: Path, modes=('off', 'spectral')) -> dict:
    clean, sr = read_mono_pcm16(clean_path)
    noisy, sr_noisy = read_mono_pcm16(noisy_path)
    if sr != sr_noisy or len(clean) != len(noisy):
        raise ValueError('Clean/noisy WAVs must be aligned with matching rate and length')
    if len(clean) > sr * 30 or len(clean) < sr // 5:
        raise ValueError('Clips must be between 0.2 and 30 seconds')
    ref_bytes, _ = enhance_pcm16_wav(clean_path.read_bytes(), mode='off')
    ref, ref_rate = decode_wav_bytes(ref_bytes)
    signal_active = np.abs(ref) > 0.025
    if not np.any(signal_active):
        raise ValueError('Reference has no audible speech-like signal')
    # This is a *signal-only* indicator, not objective speech intelligibility.
    noise_only = ~signal_active
    results = {}
    for mode in modes:
        start = time.perf_counter()
        output_bytes, metadata = enhance_pcm16_wav(noisy_path.read_bytes(), mode=mode)
        processing_ms = round(1000 * (time.perf_counter() - start), 3)
        result, rate = decode_wav_bytes(output_bytes)
        if rate != ref_rate or len(result) != len(ref):
            raise AssertionError('Enhancement changed sample duration or output rate')
        duration = len(result) / rate
        result_info = {'snr_db': snr_db(ref, result), 'si_sdr_db': si_sdr_db(ref, result),
                       'rmse': round(rms(ref - result), 6),
                       'processing_ms': processing_ms,
                       'real_time_factor': round(processing_ms / (duration * 1000), 5),
                       'output_sample_rate_hz': rate,
                       'output_duration_seconds': round(duration, 3)}
        if int(noise_only.sum()) > max(1000, len(ref) // 10):
            result_info['noise_only_rms'] = round(rms(result[noise_only]), 6)
        results[mode] = result_info
    comparison = {
        'snr_delta_db': round(results['spectral']['snr_db'] - results['off']['snr_db'], 3)
            if 'spectral' in results and 'off' in results else None,
        'si_sdr_delta_db': round(results['spectral']['si_sdr_db'] - results['off']['si_sdr_db'], 3)
            if 'spectral' in results and 'off' in results else None,
    }
    if 'noise_only_rms' in results.get('off', {}) and 'noise_only_rms' in results.get('spectral', {}):
        comparison['noise_only_attenuation_db'] = round(20 * math.log10(
            (results['off']['noise_only_rms'] + 1e-8) /
            (results['spectral']['noise_only_rms'] + 1e-8)), 3)
    return {'input_sample_rate_hz': sr, 'samples': len(clean), 'modes': results,
            'spectral_minus_raw': comparison}


def create_synthetic_manifest(directory: Path) -> Path:
    """Use offline espeak voice as surrogate; no claim of natural Telugu speech."""
    if not shutil.which('espeak'):
        raise RuntimeError('espeak CLI is required to generate optional synthetic fixtures')
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        original = Path(temporary) / 'utterance.wav'
        subprocess.run(['espeak', '-v', 'en-us', '-s', '125', '-w', str(original),
                        'The neural network is overfitting. I used a validation split and regularization.'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with wave.open(str(original), 'rb') as wav:
            original_rate = wav.getframerate()
            original_samples = np.frombuffer(wav.readframes(wav.getnframes()), '<i2').astype(float) / 32768
    cases = []
    for rate in (8000, 16000):
        # Clean base contains 0.4 sec leading and 0.4 sec trailing silence.
        from math import gcd
        g = gcd(rate, original_rate)
        converted = resample_poly(original_samples, rate // g, original_rate // g)
        clean = np.concatenate([np.zeros(int(rate * .4)), converted, np.zeros(int(rate * .4))])
        peak = max(abs(clean))
        clean = clean * (.5 / peak)
        rng = np.random.default_rng(2000 + rate)
        noise_unit = rng.normal(0, 1, len(clean))
        noise_unit += 0.6 * np.sin(2 * np.pi * 95 * np.arange(len(clean)) / rate)
        noise_unit = noise_unit / rms(noise_unit)
        for snr in (0, 10):
            noise = noise_unit * rms(clean) / 10**(snr / 20)
            noisy = np.clip(clean + noise, -.95, .95)
            identifier = f'espeak_{rate//1000}k_{snr}dB'
            write_wav(directory / f'{identifier}_clean.wav', clean, rate)
            write_wav(directory / f'{identifier}_noisy.wav', noisy, rate)
            cases.append({'id': identifier, 'clean': f'{identifier}_clean.wav',
                          'noisy': f'{identifier}_noisy.wav', 'language': 'en-US',
                          'provenance': 'synthetic espeak speech + generated stationary/noisy mixture',
                          'nominal_snr_db': snr})
    manifest = {'source': 'synthetic_offline_espeak_not_real_recordings',
                'purpose': 'audio signal sanity check, not human intelligibility or Prisma WER',
                'cases': cases}
    path = directory / 'manifest.json'
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return path


def run_manifest(path: Path, modes=('off', 'spectral')) -> dict:
    manifest = json.loads(path.read_text(encoding='utf-8'))
    cases = manifest.get('cases', [])
    if not cases or len(cases) > 100:
        raise ValueError('Expected 1–100 paired reference cases')
    results = []
    for case in cases:
        paths = [(path.parent / case[k]).resolve() for k in ('clean', 'noisy')]
        for audio_path in paths:
            if not audio_path.is_relative_to(path.parent.resolve()):
                raise ValueError('Manifest path traversal blocked')
        report = measure_pair(paths[0], paths[1], modes=modes)
        results.append({'id': case['id'], 'language': case.get('language'),
                        'provenance': case.get('provenance', manifest.get('source')), **report})
    def avg(key):
        values = [r['spectral_minus_raw'][key] for r in results
                  if r['spectral_minus_raw'].get(key) is not None]
        return round(float(np.mean(values)), 3) if values else None
    return {'source': manifest.get('source', 'user-provided paired WAV files'),
            'n_clips': len(results), 'asr_provider_calls': 0,
            'aggregate': {'mean_snr_delta_db': avg('snr_delta_db'),
                          'mean_si_sdr_delta_db': avg('si_sdr_delta_db'),
                          'mean_noise_only_attenuation_db': avg('noise_only_attenuation_db')},
            'cases': results,
            'limitations': [
                'SNR/SI-SDR are signal-fidelity measures, not speech-recognition accuracy or human intelligibility.',
                'Synthetic espeak audio is not a natural Telugu-English telephony sample.',
                'Spectral gating may suppress noise while harming phonemes; run real paired WER evaluation separately.',
                'Real-time-factor excludes browser capture and remote Gnani provider latency.',
                'No human listening test, PESQ/STOI, or deepfilter3 benchmark was run unless explicitly reported.'
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--make-synthetic-fixtures', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output', type=Path, default=Path('reports/noise_quality.json'))
    args = parser.parse_args()
    if not (args.make_synthetic_fixtures or args.manifest):
        parser.error('Provide --make-synthetic-fixtures or --manifest')
    manifest = create_synthetic_manifest(args.make_synthetic_fixtures) if args.make_synthetic_fixtures else args.manifest
    report = run_manifest(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Noise-quality benchmark:', json.dumps(report['aggregate']))
    print('Full report:', args.output)


if __name__ == '__main__':
    main()
