# Independent noise cancellation evaluation — 9 November 2026

## Purpose and evaluated algorithm

Evaluate the bundled **spectral-gating** preprocessing filter separately from interview scoring, real Gnani transcription, and the optional DeepFilterNet3 model. Enhancement is opt-in and disabled by default. Both raw and spectral paths resample 8-kHz audio to provider-compatible 16 kHz.

## Methods

Paired clean and noisy audio generated **locally** from an offline `espeak` English speech synthesizer. Four controlled fixtures: 8 kHz or 16 kHz at nominal 0 dB or 10 dB SNR, seeded additive noise and low-frequency hum. Files are synthetic and not representative of natural Telugu-English noisy telephone calls.

For each pair, the exact same clean reference is compared against the raw and spectrally filtered noisy signal. Metrics: signal-to-noise ratio (SNR), scale-invariant signal-to-distortion ratio (SI-SDR), noise-only RMS attenuation, and processing real-time factor (RTF). The report includes processing time but excludes upload/network/provider latency. The code makes **zero** Gnani API requests.

| Fixture | ΔSNR (dB) | ΔSI-SDR (dB) | Noise-only attenuation (dB) |
|---|---:|---:|---:|
| 8 kHz, 0 dB | +3.523 | +2.308 | +3.910 |
| 8 kHz, 10 dB | +2.611 | +2.381 | +3.100 |
| 16 kHz, 0 dB | +3.638 | +2.577 | +3.917 |
| 16 kHz, 10 dB | +2.880 | +2.640 | +3.089 |
| **Mean over four clips** | **+3.163** | **+2.477** | **+3.504** |

The synthetic average is not a population estimate; the clips have correlated sources and only two noise levels. RTF should be remeasured on the deployment hardware. Refer to `reports/noise_quality_synthetic.json` for exact individual metrics and provenance.

## Critical interpretation

The tested spectral gate improved signal-fidelity measures on these **four synthetic fixtures**. This does **not** demonstrate improvement in Prisma WER, Telugu transcription, intelligibility, perceived voice quality, or production telephony. Neural DeepFilterNet3 has not been benchmarked. In a noisy ASR system, removing background noise can still erase phonemes or harm word recognition.

## Reproduce

```
python -m eval_harness.noise_quality --manifest reports/noise_fixtures/manifest.json --output reports/noise_quality_recheck.json
python -m pytest tests/test_noise_enhancement.py tests/test_noise_quality.py -q
# To make fresh test audio instead, install espeak and run:
python -m eval_harness.noise_quality --make-synthetic-fixtures reports/noise_fixtures --output reports/noise_quality_synthetic.json
```

The first command requires `espeak` installed for *synthetic English voice generation*. Alternatively pass your own consented paired audio through `--manifest path/manifest.json`. See `eval_harness/noise_quality.py`.

## Follow-up production evaluation (not run)

1. Collect separately consented Telugu, English and Telugu-English clean/noisy recordings, including 8-kHz compressed telephony and nonstationary noise.
2. Have a human transcribe the clean utterances independently, checking technical terms and proper nouns.
3. Compare **raw vs spectral vs DeepFilterNet3** with paired clips and actual Gnani Prisma calls via `python -m eval_harness.asr_ab --manifest ... --run-live`. The existing ASR script compares raw against spectral only; add neural as a third branch when installed.
4. Compute WER/CER and critical-term preservation, p50/p95 latency, failures by language/noise type; inspect per-utterance deterioration.
5. Choose enhancement only when transcript quality is improved or at least not worsened at acceptable latency. Do not select on synthetic SNR alone.
