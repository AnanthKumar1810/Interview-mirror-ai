'use strict';

/**
 * AudioWorklet processor: captures mic input from channel 0, accumulates in
 * a ring buffer, resamples from device sampleRate to 16000 Hz using a windowed
 * sinc FIR filter (anti-aliasing bandlimited interpolation), packetizes into
 * exactly 512 samples (1024 bytes) per frame of signed 16-bit little-endian PCM,
 * and posts each frame at 32ms realtime cadence (no burst buffering).
 *
 * Runs in AudioWorkletGlobalScope — no DOM access, no external imports.
 */
class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // Device sample rate (from global sampleRate or this.sampleRate)
    this._deviceRate = (typeof sampleRate !== 'undefined' ? sampleRate : 0) || (this && this.sampleRate) || 16000;
    this._targetRate = 16000;
    this._step = this._deviceRate / this._targetRate;

    // Filter configuration for anti-aliasing sinc resampling
    // If device rate matches target rate, filter is bypassed
    this._isNativeRate = Math.abs(this._deviceRate - this._targetRate) < 1;
    this._filterTapsHalf = 8; // K = 8 taps on each side (total 17 taps)
    // Lowpass cutoff: slightly below Nyquist of target rate (7.2 kHz normalized to input rate)
    this._cutoff = (7200 / this._deviceRate);

    // Ring buffer for raw input samples (Float32)
    // 65536 samples provides >1.3s buffer at 48kHz
    this._ringSize = 65536;
    this._ring = new Float32Array(this._ringSize);
    this._writePos = 0;
    this._readPos = 0.0;

    this._stopped = false;

    this.port.onmessage = (event) => {
      if (event.data && event.data.type === 'stop') {
        this._flush();
        this._stopped = true;
      }
    };
  }

  /**
   * Evaluate windowed sinc bandlimited interpolation sample at continuous time `pos`.
   */
  _interpolateSample(pos) {
    if (this._isNativeRate) {
      const idx = ((Math.round(pos) % this._ringSize) + this._ringSize) % this._ringSize;
      return this._ring[idx];
    }

    const center = Math.round(pos);
    const K = this._filterTapsHalf;
    const fc = this._cutoff;
    let sum = 0;
    let weightSum = 0;

    for (let k = -K; k <= K; k++) {
      const n = center + k;
      const delta = pos - n;
      const absDelta = Math.abs(delta);

      if (absDelta <= K) {
        // Hann window
        const w = 0.5 + 0.5 * Math.cos((Math.PI * delta) / K);
        // Sinc: sin(2 * pi * fc * delta) / (pi * delta)
        let sinc;
        if (absDelta < 1e-7) {
          sinc = 2 * fc;
        } else {
          sinc = Math.sin(2 * Math.PI * fc * delta) / (Math.PI * delta);
        }
        const weight = sinc * w;
        const ringIdx = ((n % this._ringSize) + this._ringSize) % this._ringSize;
        sum += this._ring[ringIdx] * weight;
        weightSum += weight;
      }
    }

    return weightSum > 1e-6 ? (sum / weightSum) : 0;
  }

  _flush() {
    const remainingInput = this._writePos - this._readPos;
    if (remainingInput > 1) {
      const pcm = new Int16Array(512); // 512 samples = 1024 bytes, zero-padded
      const count = Math.min(512, Math.floor(remainingInput / this._step));
      for (let i = 0; i < count; i++) {
        const pos = this._readPos + i * this._step;
        const sample = this._interpolateSample(pos);
        const clamped = Math.max(-1, Math.min(1, sample));
        pcm[i] = clamped < 0 ? (clamped * 32768) | 0 : (clamped * 32767) | 0;
      }
      this._readPos += count * this._step;
      this.port.postMessage({ type: 'audio', buffer: pcm });
    }
  }

  process(inputs) {
    if (this._stopped) return false;

    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;

    const channel0 = input[0];
    const len = channel0.length;

    // Accumulate input samples from channel 0 into ring buffer
    for (let i = 0; i < len; i++) {
      this._ring[this._writePos % this._ringSize] = channel0[i];
      this._writePos++;
    }

    // Packetize exactly 512 samples (1024 bytes) per frame.
    // 512 samples @ 16kHz = exactly 32ms of audio.
    // Maintain 32ms realtime cadence and prevent bursting.
    const neededInput = Math.ceil(this._readPos + (512 - 1) * this._step + this._filterTapsHalf + 1);
    if (this._writePos >= neededInput) {
      const pcm = new Int16Array(512);
      for (let i = 0; i < 512; i++) {
        const pos = this._readPos + i * this._step;
        const sample = this._interpolateSample(pos);
        const clamped = Math.max(-1, Math.min(1, sample));
        pcm[i] = clamped < 0 ? (clamped * 32768) | 0 : (clamped * 32767) | 0;
      }
      this._readPos += 512 * this._step;
      this.port.postMessage({ type: 'audio', buffer: pcm });
    }

    return true;
  }
}

registerProcessor('pcm-capture', PCMCaptureProcessor);
