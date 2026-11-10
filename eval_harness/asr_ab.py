"""Opt-in, real Prisma ASR benchmark: raw vs enhanced speech on consented WAVs.

This script makes TWO paid STT requests per clip. No live calls without
--run-live AND GNANI_API_KEY. Output contains aggregate errors, never audio or
transcripts. Audio references and expected transcripts stay on your device.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
import unicodedata
from pathlib import Path

from audio_tools import inspect_pcm16_wav
from gnani import GnaniClient
from speech_enhancement import enhance_pcm16_wav


def normalized_words(text: str) -> list[str]:
    """Keep Indic combining marks intact; basic whitespace-token WER metric."""
    normalized = unicodedata.normalize("NFKC", text.casefold())
    cleaned = ''.join(char if unicodedata.category(char)[0] in {'L', 'M', 'N'} else ' '
                      for char in normalized)
    return cleaned.split()


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, start=1):
        current = [i]
        for j, observed in enumerate(hypothesis, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (expected != observed)))
        previous = current
    return previous[-1]


def word_error_rate(reference: str, actual: str) -> float:
    expected = normalized_words(reference)
    if not expected:
        raise ValueError("Reference transcript must contain words")
    return round(edit_distance(expected, normalized_words(actual)) / len(expected), 4)


def _percentile(numbers: list[float], fraction: float) -> float:
    vals = sorted(numbers)
    return round(vals[max(0, int((len(vals) - 1) * fraction))], 1)


def run_live(manifest: dict, base_dir: Path, max_clips: int) -> dict:
    cases = manifest.get('cases', [])
    if not isinstance(cases, list) or not 1 <= len(cases) <= max_clips:
        raise ValueError('Manifest must include 1 to max_clips cases')
    client = GnaniClient()
    if not client.enabled:
        raise RuntimeError('GNANI_API_KEY must be configured for live testing')
    results = []
    try:
        for case in cases:
            if case.get('consent_for_provider') is not True:
                raise ValueError('Every clip requires explicit consent_for_provider=true')
            audio_path = (base_dir / case['path']).resolve()
            if not audio_path.is_relative_to(base_dir.resolve()):
                raise ValueError('Audio path must be inside the manifest directory')
            raw = audio_path.read_bytes()
            inspect_pcm16_wav(raw)
            language = case['language']
            reference = case['reference_transcript']
            item = {'id': case['id'], 'language': language, 'durations_ms': {}, 'wer': {}}
            for mode in ('off', 'spectral'):
                provider_wav, _ = enhance_pcm16_wav(raw, mode=mode)
                start = time.perf_counter()
                transcript = client.transcribe(provider_wav, language)['transcript']
                item['durations_ms'][mode] = round((time.perf_counter() - start) * 1000, 1)
                item['wer'][mode] = word_error_rate(reference, transcript)
            results.append(item)
    finally:
        client.client.close()
    return {
        'n_clips': len(results), 'provider_calls': len(results) * 2,
        'mean_wer_raw': round(statistics.mean(r['wer']['off'] for r in results), 4),
        'mean_wer_spectral': round(statistics.mean(r['wer']['spectral'] for r in results), 4),
        'mean_latency_raw_ms': round(statistics.mean(r['durations_ms']['off'] for r in results), 1),
        'mean_latency_spectral_ms': round(statistics.mean(r['durations_ms']['spectral'] for r in results), 1),
        'cases': results,
        'limitations': [
            'WER is whitespace-token based; interpret results cautiously for Telugu and code-mixed speech.',
            'Transcript quality can degrade after spectral gating; never assume improvement.',
            'Clip references must be independently transcribed and reviewed for meaningful WER.',
            'Results are exploratory unless clip count and conditions support meaningful inference.'
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Compare real Prisma WER on original and enhanced audio')
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', default='reports/asr_ab_live.json', type=Path)
    parser.add_argument('--run-live', action='store_true', help='Explicit permission to spend Gnani credits')
    parser.add_argument('--max-clips', type=int, default=20)
    args = parser.parse_args()
    if not args.run_live:
        parser.error('This makes paid external API requests. Supply --run-live explicitly.')
    if args.max_clips < 1 or args.max_clips > 100:
        parser.error('max-clips must be in 1..100')
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    report = run_live(manifest, args.manifest.resolve().parent, args.max_clips)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"WER raw={report['mean_wer_raw']} spectral={report['mean_wer_spectral']} (n={report['n_clips']}); report: {args.output}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
