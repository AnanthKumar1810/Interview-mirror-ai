'use strict';

/**
 * AudioWorklet processor: captures mic input from channel 0, accumulates in
 * a ring buffer, resamples from device sampleRate to 16000 Hz using linear
 * interpolation, packetizes into exactly 512 samples (1024 bytes) per frame
 * of signed 16-bit little-endian PCM, and posts each frame at 32ms realtime
 * cadence (no burst buffering).
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

    // Ring buffer for raw input samples (Float32)
    // 65536 samples provides >1s buffer at 48kHz
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

  _flush() {
    const remainingInput = this._writePos - this._readPos;
    if (remainingInput > 1) {
      const pcm = new Int16Array(512); // 512 samples = 1024 bytes, zero-padded
      const count = Math.min(512, Math.floor(remainingInput / this._step));
      for (let i = 0; i < count; i++) {
        const pos = this._readPos + i * this._step;
        const idx0 = Math.floor(pos);
        const idx1 = idx0 + 1;
        const frac = pos - idx0;
        const s0 = this._ring[idx0 % this._ringSize];
        const s1 = idx1 < this._writePos ? this._ring[idx1 % this._ringSize] : s0;
        const sample = s0 + (s1 - s0) * frac;
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
    // We emit at most 1 frame per process() call to maintain 32ms realtime cadence and prevent bursting.
    const neededInput = Math.ceil(this._readPos + (512 - 1) * this._step + 1);
    if (this._writePos >= neededInput) {
      const pcm = new Int16Array(512);
      for (let i = 0; i < 512; i++) {
        const pos = this._readPos + i * this._step;
        const idx0 = Math.floor(pos);
        const idx1 = idx0 + 1;
        const frac = pos - idx0;
        const s0 = this._ring[idx0 % this._ringSize];
        const s1 = this._ring[idx1 % this._ringSize];
        const sample = s0 + (s1 - s0) * frac;
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
