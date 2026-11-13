'use strict';

/**
 * RealtimeInterviewClient — Browser WebSocket client for InterviewMirror's
 * realtime streaming voice pipeline.
 *
 * Connects to ws://HOST/ws/interview?protocol_version=1.0.
 * Handles bidirectional communication: JSON control frames + binary PCM/WAV frames.
 * Emits EventTarget events:
 *   - 'connected'
 *   - 'disconnected'
 *   - 'session_ack'
 *   - 'transcript'
 *   - 'turn_state'
 *   - 'tts_audio'
 *   - 'provider_event'
 *   - 'error'
 *   - 'metrics'
 */
class RealtimeInterviewClient extends EventTarget {
  /**
   * @param {Object} [opts]
   * @param {string} [opts.host] - Host and port (defaults to window.location.host)
   */
  constructor(opts = {}) {
    super();
    this._host = opts.host || (typeof window !== 'undefined' && window.location ? window.location.host : 'localhost:8000');
    this._ws = null;
    this._seq = 0;
    this._lastServerSeq = -1;

    // Audio capture (AudioWorklet)
    this._audioCtx = null;
    this._workletNode = null;
    this._micStream = null;

    // TTS playback
    this._ttsCtx = null;
    this._ttsNextTime = 0;
    this._ttsSources = [];
  }

  get connected() {
    return this._ws !== null && this._ws.readyState === WebSocket.OPEN;
  }

  /**
   * Connect to the WebSocket endpoint and send session_start.
   * Server handles all API authentication; no API keys are sent from browser.
   *
   * @param {Object} params
   * @param {string} params.track - Interview track (agentic, ai, software)
   * @param {string} params.language - Language code (e.g. en-IN, te-IN, hi-IN)
   * @param {boolean} params.consent - Explicit user audio consent
   */
  connect(params = {}) {
    if (this.connected) return Promise.resolve();
    if (this._ws) return Promise.reject(new Error('Connection already in progress'));

    const protocol = (typeof window !== 'undefined' && window.location && window.location.protocol === 'https:') ? 'wss' : 'ws';
    const url = `${protocol}://${this._host}/ws/interview?protocol_version=1.0`;

    this._ws = new WebSocket(url);
    this._ws.binaryType = 'arraybuffer';
    return new Promise((resolve, reject) => {

    this._ws.onopen = () => {
      this._send({
        type: 'session_start',
        protocol_version: '1.0',
        track: params.track || 'agentic',
        language: params.language || 'en-IN',
        consent_given: !!params.consent,
        stt_model: params.stt_model || 'prisma-v2.5',
        timestamp_ms: Date.now()
      });
      resolve();
      this.dispatchEvent(new Event('connected'));
    };

    this._ws.onmessage = (event) => {
      this._handleIncomingMessage(event);
    };

    this._ws.onclose = (event) => {
      this._ws = null;
      this.stopCapture({ commit: false });
      this.stopTTS();
      this.dispatchEvent(new CustomEvent('disconnected', {
        detail: {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean
        }
      }));
    };

    this._ws.onerror = (err) => {
      reject(new Error('WebSocket connection error'));
      this.dispatchEvent(new CustomEvent('error', {
        detail: { message: 'WebSocket connection error', error: err }
      }));
    };
    });
  }

  /**
   * Close the WebSocket connection and stop audio devices.
   */
  disconnect() {
    this.stopCapture({ commit: false });
    this.stopTTS();
    if (this._ws) {
      try {
        this._ws.close(1000, 'Normal closure by client');
      } catch (_) {}
      this._ws = null;
    }
  }

  /**
   * Send a JSON control message with tracked sequence number.
   * @param {Object} msg
   */
  _send(msg) {
    if (!this.connected) return;
    msg.sequence_number = this._seq;
    this._seq = (this._seq + 1) % 0x100000000;
    this._ws.send(JSON.stringify(msg));
  }

  /**
   * Send binary PCM audio frame to the WebSocket server.
   * @param {ArrayBuffer|ArrayBufferView} data - 512 samples / 1024 bytes signed 16-bit PCM
   */
  sendAudio(data) {
    if (!this.connected) return;
    if (data instanceof ArrayBuffer) {
      this._ws.send(data);
    } else if (data && data.buffer instanceof ArrayBuffer) {
      // Send the ArrayBufferView directly or slice if sub-range
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
   * Internal message handler.
   */
  _handleIncomingMessage(event) {
    if (typeof event.data === 'string') {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (_) {
        return;
      }

      if (typeof msg.sequence_number === 'number') {
        this._lastServerSeq = msg.sequence_number;
      }

      const type = msg.type;
      if (!type) return;

      // Handle speech_start interruption from server
      if (type === 'speech_start' ||
          (type === 'provider_event' && (msg.event === 'speech_start' || msg.event_name === 'speech_start'))) {
        this.stopTTS();
      }

      // Handle ping/pong heartbeat
      if (type === 'ping') {
        this._send({ type: 'pong', timestamp_ms: Date.now() });
        return;
      }

      // Emit specific events
      switch (type) {
        case 'session_ack':
        case 'transcript':
        case 'turn_state':
        case 'tts_audio':
        case 'tts_audio_meta':
        case 'provider_event':
        case 'error':
        case 'metrics':
          this.dispatchEvent(new CustomEvent(type, { detail: msg }));
          break;
        default:
          this.dispatchEvent(new CustomEvent(type, { detail: msg }));
          break;
      }
    } else if (event.data instanceof ArrayBuffer) {
      // Binary message: TTS audio chunk (PCM/WAV)
      this._scheduleTTSChunk(event.data);
      this.dispatchEvent(new CustomEvent('tts_audio', { detail: { data: event.data } }));
    }
  }

  // ── TTS Gapless Playback & Interruption ──────────────────────────────

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

  /**
   * Schedule incoming audio chunk for gapless playback using AudioContext.
   */
  _scheduleTTSChunk(arrayBuffer) {
    const ctx = this._getOrCreateTTSContext();
    const bytes = new Uint8Array(arrayBuffer);

    // Detect RIFF/WAVE header
    const isWav = bytes.length >= 12 &&
      bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 && // RIFF
      bytes[8] === 0x57 && bytes[9] === 0x41 && bytes[10] === 0x56 && bytes[11] === 0x45; // WAVE

    if (isWav) {
      ctx.decodeAudioData(arrayBuffer.slice(0)).then((decoded) => {
        this._queueAudioBuffer(decoded);
      }).catch(() => {});
    } else {
      // Raw 16kHz mono 16-bit signed PCM
      const sampleCount = Math.floor(bytes.length / 2);
      if (sampleCount <= 0) return;
      const buffer = ctx.createBuffer(1, sampleCount, 16000);
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

    this._ttsSources.push(source);
    source.onended = () => {
      const idx = this._ttsSources.indexOf(source);
      if (idx !== -1) {
        this._ttsSources.splice(idx, 1);
      }
    };
  }

  /**
   * Stop TTS playback immediately (used on user interruption / speech_start).
   */
  stopTTS() {
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
  }

  // ── AudioWorklet Microphone Capture ──────────────────────────────────

  /**
   * Start microphone capture using AudioWorklet (static/audio-worklet.js).
   */
  async startCapture() {
    if (this._workletNode) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Microphone access requires a modern browser and HTTPS/localhost.');
    }

    this._micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1
      }
    });

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    this._audioCtx = new AudioCtx();

    await this._audioCtx.audioWorklet.addModule('/static/audio-worklet.js');

    this._workletNode = new AudioWorkletNode(this._audioCtx, 'pcm-capture');

    const source = this._audioCtx.createMediaStreamSource(this._micStream);
    source.connect(this._workletNode);

    // Muted node to destination to keep processing graph active without feedback
    const mute = this._audioCtx.createGain();
    mute.gain.value = 0;
    this._workletNode.connect(mute);
    mute.connect(this._audioCtx.destination);

    // Receive 512-sample PCM frames from worklet and stream via WS
    this._workletNode.port.onmessage = (event) => {
      if (event.data && event.data.type === 'audio' && event.data.buffer) {
        this.sendAudio(event.data.buffer);
      }
    };
  }

  /**
   * Stop microphone capture and tear down AudioWorklet and AudioContext.
   */
  async stopCapture({ commit = true } = {}) {
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
    if (commit) this._send({ type: 'end_audio' });
  }
}

// Expose on window for app.js
if (typeof window !== 'undefined') {
  window.RealtimeInterviewClient = RealtimeInterviewClient;
}
