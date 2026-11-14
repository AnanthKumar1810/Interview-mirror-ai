'use strict';

/**
 * RealtimeInterviewClient — Browser WebSocket client for hands-free
 * spoken interview practice.
 *
 * Connects to ws://HOST/ws/interview?protocol_version=1.0.
 * Handles continuous bidirectional streaming:
 *   - Emits 512-sample (1024-byte) 16kHz PCM audio frames @ 32ms cadence
 *   - Receives turn_state, live transcripts, and TTS audio chunks
 *   - Schedules gapless TTS playback on AudioContext timeline
 *   - Supports immediate, debounced barge-in interruption on user speech
 *   - Reports playback_start, playback_stop, and barge_in telemetry to server
 *   - Emits events: connected, disconnected, session_ack, turn_state,
 *     transcript, reprompt, metrics, error
 */
class RealtimeInterviewClient extends EventTarget {
  constructor(opts = {}) {
    super();
    this._host = opts.host || (typeof window !== 'undefined' && window.location ? window.location.host : 'localhost:8000');
    this._ws = null;
    this._seq = 0;
    this._generationId = 0;
    this._sessionId = null;

    // Audio capture (AudioWorklet)
    this._audioCtx = null;
    this._workletNode = null;
    this._micStream = null;

    // TTS playback
    this._ttsCtx = null;
    this._ttsNextTime = 0;
    this._ttsSources = [];
    this._isSpeaking = false;
    this._connectPending = null;
    this._ttsCompleteGeneration = -1;
    this._ttsSampleRate = 24000;

    // Barge-in debouncing & noise floor tracking
    this._noiseFloor = 200.0;
    this._bargeInConsecutiveFrames = 0;
  }

  get connected() {
    return this._ws !== null && this._ws.readyState === WebSocket.OPEN;
  }

  get isSpeaking() {
    return this._isSpeaking;
  }

  preparePlayback() {
    // A context created during the Start gesture can play the later TTS
    // response under browser autoplay rules.
    return this._getOrCreateTTSContext();
  }

  /**
   * Connect to WebSocket endpoint and initiate interview session.
   *
   * @param {Object} params
   * @param {string} params.track - Interview track (agentic, ai, software)
   * @param {string} params.language - Language code (en-IN, te-IN, hi-IN)
   * @param {boolean} params.consent - Explicit user audio consent
   * @param {string} [params.stt_model] - 'prisma-v2.5' or 'prisma-v3.0'
   * @param {string} [params.session_id] - Optional pre-created session ID
   * @param {string} [params.token] - Optional JWT bearer token for authenticated sessions
   * @param {string} [params.endpointing_policy] - 'fixed', 'two_stage', or 'adaptive'
   */
  connect(params = {}) {
    if (this.connected && this._sessionId) return Promise.resolve(this._sessionId);
    if (this._connectPending) return this._connectPending.promise;
    if (this._ws) return Promise.reject(new Error('WebSocket connection is already opening.'));

    let resolveConnect, rejectConnect;
    const promise = new Promise((resolve, reject) => {
      resolveConnect = resolve;
      rejectConnect = reject;
    });
    const timer = setTimeout(() => {
      rejectConnect(new Error('Interview connection timed out.'));
      this._connectPending = null;
      this.disconnect();
    }, 15000);
    this._connectPending = { promise, resolve: resolveConnect, reject: rejectConnect, timer };

    const protocol = (typeof window !== 'undefined' && window.location && window.location.protocol === 'https:') ? 'wss' : 'ws';
    const url = `${protocol}://${this._host}/ws/interview?protocol_version=1.0`;

    this._ws = new WebSocket(url);
    this._ws.binaryType = 'arraybuffer';

    this._ws.onopen = () => {
      this._send({
        type: 'session_start',
        protocol_version: '1.0',
        track: params.track || 'agentic',
        language: params.language || 'en-IN',
        consent_given: !!params.consent,
        stt_model: params.stt_model || 'prisma-v2.5',
        session_id: params.session_id || null,
        token: params.token || null,
        endpointing_policy: params.endpointing_policy || 'adaptive',
        github_repo: params.github_repo || null,
        resume_text: params.resume_text || null,
        timestamp_ms: Date.now()
      });
      this.dispatchEvent(new Event('connected'));
    };

    this._ws.onmessage = (event) => {
      this._handleIncomingMessage(event);
    };

    this._ws.onclose = (event) => {
      this._rejectConnect(new Error(`Interview connection closed (${event.code}).`));
      this._ws = null;
      this.stopCapture();
      this.stopTTS();
      this.dispatchEvent(new CustomEvent('disconnected', {
        detail: { code: event.code, reason: event.reason, wasClean: event.wasClean }
      }));
    };

    this._ws.onerror = (err) => {
      this._rejectConnect(new Error('WebSocket communication error.'));
      this.dispatchEvent(new CustomEvent('error', {
        detail: { message: 'WebSocket communication error', error: err }
      }));
    };
    return promise;
  }

  _rejectConnect(error) {
    if (!this._connectPending) return;
    clearTimeout(this._connectPending.timer);
    this._connectPending.reject(error);
    this._connectPending = null;
  }

  /**
   * Gracefully request interview completion from server.
   */
  endInterview() {
    if (this.connected) {
      this._send({ type: 'end_interview', session_id: this._sessionId });
    }
    this.stopCapture();
    this.stopTTS();
  }

  /**
   * Disconnect and close all audio resources.
   */
  disconnect() {
    this._rejectConnect(new Error('Interview connection cancelled.'));
    this.stopCapture();
    this.stopTTS();
    if (this._ws) {
      try {
        this._ws.close(1000, 'Client disconnected');
      } catch (_) {}
      this._ws = null;
    }
  }

  /**
   * Send JSON control message with tracked sequence number.
   */
  _send(msg) {
    if (!this.connected) return;
    msg.sequence_number = this._seq;
    this._seq = (this._seq + 1) % 0x100000000;
    this._ws.send(JSON.stringify(msg));
  }

  /**
   * Send binary PCM audio frame to the WebSocket server.
   */
  sendAudio(data) {
    if (!this.connected) return;
    if (data instanceof ArrayBuffer) {
      this._ws.send(data);
    } else if (data && data.buffer instanceof ArrayBuffer) {
      if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
        this._ws.send(data.buffer);
      } else {
        this._ws.send(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength));
      }
    } else {
      this._ws.send(data);
    }
  }

  /**
   * Signal candidate barge-in when candidate starts speaking over interviewer.
   */
  bargeIn() {
    if (!this._isSpeaking) return;
    this.stopTTS();
    this._generationId++;
    this._send({
      type: 'barge_in',
      generation_id: this._generationId,
      timestamp_ms: Date.now()
    });
    this.dispatchEvent(new Event('barge_in'));
  }

  _handleIncomingMessage(event) {
    if (typeof event.data === 'string') {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (_) {
        return;
      }

      const type = msg.type;
      if (!type) return;

      if (type === 'ping') {
        this._send({ type: 'pong', timestamp_ms: Date.now() });
        return;
      }

      if (type === 'session_ack') {
        this._sessionId = msg.session_id;
        if (this._connectPending) {
          clearTimeout(this._connectPending.timer);
          this._connectPending.resolve(msg.session_id);
          this._connectPending = null;
        }
      }

      if (type === 'tts_audio_meta') {
        if (typeof msg.generation_id === 'number') {
          this._generationId = msg.generation_id;
        }
        if (Number.isInteger(msg.sample_rate) && msg.sample_rate > 0) {
          this._ttsSampleRate = msg.sample_rate;
        }
        this._ttsCompleteGeneration = -1;
      }

      if (type === 'tts_complete' && msg.generation_id === this._generationId) {
        this._ttsCompleteGeneration = msg.generation_id;
        this._maybeFinishPlayback();
      }

      if (type === 'barge_in') {
        this.stopTTS();
      }

      if (type === 'turn_state') {
        if (msg.raw_state === 'completed') {
          this.stopTTS();
        }
      }

      this.dispatchEvent(new CustomEvent(type, { detail: msg }));

    } else if (event.data instanceof ArrayBuffer) {
      // Incoming TTS binary audio chunk
      this._scheduleTTSChunk(event.data);
      this.dispatchEvent(new CustomEvent('tts_audio', { detail: { data: event.data } }));
    }
  }

  // ── TTS Gapless Playback ────────────────────────────────────────────

  _getOrCreateTTSContext() {
    if (!this._ttsCtx || this._ttsCtx.state === 'closed') {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this._ttsCtx = new AudioCtx();
    }
    if (this._ttsCtx.state === 'suspended') {
      this._ttsCtx.resume();
    }
    return this._ttsCtx;
  }

  _scheduleTTSChunk(arrayBuffer) {
    const ctx = this._getOrCreateTTSContext();
    const bytes = new Uint8Array(arrayBuffer);

    // Check RIFF/WAVE header
    const isWav = bytes.length >= 12 &&
      bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
      bytes[8] === 0x57 && bytes[9] === 0x41 && bytes[10] === 0x56 && bytes[11] === 0x45;

    if (isWav) {
      ctx.decodeAudioData(arrayBuffer.slice(0)).then((decoded) => {
        this._queueAudioBuffer(decoded);
      }).catch(() => {});
    } else {
      // 24kHz or 16kHz mono 16-bit signed PCM
      const sampleCount = Math.floor(bytes.length / 2);
      if (sampleCount <= 0) return;
      const buffer = ctx.createBuffer(1, sampleCount, this._ttsSampleRate);
      const channel = buffer.getChannelData(0);
      const view = new DataView(arrayBuffer);
      for (let i = 0; i < sampleCount; i++) {
        channel[i] = view.getInt16(i * 2, true) / 32768;
      }
      this._queueAudioBuffer(buffer);
    }
  }

  _queueAudioBuffer(audioBuffer) {
    const ctx = this._ttsCtx;
    if (!ctx || ctx.state === 'closed') return;

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    const startAt = Math.max(now, this._ttsNextTime);
    source.start(startAt);
    this._ttsNextTime = startAt + audioBuffer.duration;

    // Send playback_start notification if transition from silent to speaking
    if (!this._isSpeaking) {
      this._isSpeaking = true;
      this._send({
        type: 'playback_start',
        generation_id: this._generationId,
        client_timestamp_ms: Date.now()
      });
    }

    this._ttsSources.push(source);
    source.onended = () => {
      const idx = this._ttsSources.indexOf(source);
      if (idx !== -1) {
        this._ttsSources.splice(idx, 1);
      }
      this._maybeFinishPlayback();
    };
  }

  _maybeFinishPlayback() {
    if (this._isSpeaking && this._ttsSources.length === 0 &&
        this._ttsCompleteGeneration === this._generationId) {
      this._isSpeaking = false;
      this._send({
        type: 'playback_stop',
        generation_id: this._generationId,
        client_timestamp_ms: Date.now()
      });
    }
  }

  stopTTS() {
    const wasSpeaking = this._isSpeaking;
    this._isSpeaking = false;
    this._ttsCompleteGeneration = -1;
    for (const src of this._ttsSources) {
      try {
        src.stop();
        src.disconnect();
      } catch (_) {}
    }
    this._ttsSources = [];
    if (this._ttsCtx) {
      this._ttsNextTime = this._ttsCtx.currentTime;
    } else {
      this._ttsNextTime = 0;
    }

    if (wasSpeaking) {
      this._send({
        type: 'playback_stop',
        generation_id: this._generationId,
        client_timestamp_ms: Date.now()
      });
    }
  }

  // ── AudioWorklet Microphone Capture ──────────────────────────────────

  async startCapture() {
    if (this._workletNode) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Microphone access requires HTTPS or localhost.');
    }

    this._micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1
      }
    });

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    this._audioCtx = new AudioCtx();

    await this._audioCtx.audioWorklet.addModule('/static/audio-worklet.js');
    this._workletNode = new AudioWorkletNode(this._audioCtx, 'pcm-capture');

    const source = this._audioCtx.createMediaStreamSource(this._micStream);
    source.connect(this._workletNode);

    // Muted node to destination keeps audio pipeline running without feedback
    const mute = this._audioCtx.createGain();
    mute.gain.value = 0;
    this._workletNode.connect(mute);
    mute.connect(this._audioCtx.destination);

    // Stream 512-sample PCM frames over WebSocket at 32ms cadence
    this._workletNode.port.onmessage = (event) => {
      if (event.data && event.data.type === 'audio' && event.data.buffer) {
        const buf = event.data.buffer;

        // Compute RMS frame energy
        let sumSq = 0;
        for (let i = 0; i < buf.length; i++) {
          const s = buf[i];
          sumSq += s * s;
        }
        const rms = Math.sqrt(sumSq / buf.length);

        // Update adaptive background noise floor estimation
        this._noiseFloor = 0.95 * this._noiseFloor + 0.05 * Math.min(rms, 1000.0);

        // If coach is actively speaking, evaluate debounced barge-in
        if (this._isSpeaking) {
          // Dynamic threshold: higher than background noise floor + margin
          const threshold = Math.max(1400.0, this._noiseFloor * 3.2);
          if (rms > threshold) {
            this._bargeInConsecutiveFrames++;
            // Require 3 consecutive frames (~96ms) to eliminate acoustic echo / click transients
            if (this._bargeInConsecutiveFrames >= 3) {
              this._bargeInConsecutiveFrames = 0;
              this.bargeIn();
            }
          } else {
            this._bargeInConsecutiveFrames = 0;
          }
        } else {
          this._bargeInConsecutiveFrames = 0;
        }

        this.sendAudio(event.data.buffer);
      }
    };
  }

  async stopCapture() {
    if (this._workletNode) {
      try {
        this._workletNode.port.postMessage({ type: 'stop' });
        this._workletNode.disconnect();
      } catch (_) {}
      this._workletNode = null;
    }

    if (this._micStream) {
      this._micStream.getTracks().forEach((track) => track.stop());
      this._micStream = null;
    }

    if (this._audioCtx) {
      try {
        await this._audioCtx.close();
      } catch (_) {}
      this._audioCtx = null;
    }
  }
}

if (typeof window !== 'undefined') {
  window.RealtimeInterviewClient = RealtimeInterviewClient;
}
