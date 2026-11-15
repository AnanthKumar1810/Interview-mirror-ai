import { useSyncExternalStore } from "react";
import type { SetupDraft } from "./types";

type WireMessage = { type: string; [key: string]: unknown };
type Client = EventTarget & {
  readonly connected: boolean;
  connect(options: Record<string, unknown>): Promise<string>;
  preparePlayback(): void;
  startCapture(): Promise<void>;
  endInterview(): void;
  disconnect(): void;
};

export interface RealtimeState {
  sessionId: string;
  status: string;
  rawState: string;
  question: string;
  questionNumber: number;
  totalQuestions: number;
  transcript: string;
  turns: { question: string; transcript: string; feedback?: Record<string, unknown> }[];
  error: string;
  connected: boolean;
  captureReady: boolean;
  audioProcessing: {
    echoCancellation: boolean | null;
    noiseSuppression: boolean | null;
    autoGainControl: boolean | null;
    echoCancellationSupported: boolean;
    noiseSuppressionSupported: boolean;
    autoGainControlSupported: boolean;
  } | null;
  noiseComparison: {
    status: string;
    question_number?: number | undefined;
    raw_transcript?: string | undefined;
    filtered_transcript?: string | undefined;
    exact_match?: boolean | undefined;
    enhancement_ms?: number | undefined;
    provider_latency_ms?: number | undefined;
    note?: string | undefined;
    reason?: string | undefined;
  } | null;
}

const initial: RealtimeState = {
  sessionId: "",
  status: "Ready",
  rawState: "waiting",
  question: "",
  questionNumber: 1,
  totalQuestions: 3,
  transcript: "",
  turns: [],
  error: "",
  connected: false,
  captureReady: false,
  audioProcessing: null,
  noiseComparison: null,
};
let state = initial;
let client: Client | null = null;
let audioProcessingListener: ((event: Event) => void) | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());
const update = (patch: Partial<RealtimeState>) => {
  state = { ...state, ...patch };
  notify();
};
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
export const getRealtimeState = () => state;
export function useRealtimeState() {
  return useSyncExternalStore(subscribe, getRealtimeState, () => initial);
}

function loadClient(): Promise<void> {
  if (window.RealtimeInterviewClient) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/realtime-client.js";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load the audio client."));
    document.head.appendChild(script);
  });
}

declare global {
  interface Window {
    RealtimeInterviewClient?: new () => Client;
  }
}

function handle(event: Event) {
  const msg = (event as CustomEvent<WireMessage>).detail;
  receiveRealtimeMessage(msg);
}

/** Apply one backend control event; also used by the protocol regression test. */
export function receiveRealtimeMessage(msg: WireMessage | undefined) {
  if (!msg) return;
  if (msg.type === "session_ack") {
    update({
      sessionId: String(msg["session_id"] ?? ""),
      question: String(msg["question"] ?? ""),
      questionNumber: Number(msg["question_number"] ?? 1),
      totalQuestions: Number(msg["total_questions"] ?? 3),
      connected: true,
    });
  } else if (msg.type === "turn_state") {
    const nextQuestion = String(msg["question"] ?? "");
    const nextNumber = Number(msg["question_number"] ?? state.questionNumber);
    const feedback = msg["feedback"] as Record<string, unknown> | undefined;
    const turnCompleted = feedback && typeof feedback === "object" && state.transcript.trim();
    const turns =
      turnCompleted &&
      !state.turns.some(
        (turn) => turn.transcript === state.transcript && turn.question === state.question,
      )
        ? [...state.turns, { question: state.question, transcript: state.transcript, feedback }]
        : state.turns;
    update({
      status: String(msg["state"] ?? ""),
      rawState: String(msg["raw_state"] ?? ""),
      question: nextQuestion || state.question,
      questionNumber: nextNumber,
      turns,
      transcript: nextNumber !== state.questionNumber ? "" : state.transcript,
    });
  } else if (msg.type === "transcript") {
    update({ transcript: String(msg["text"] ?? "") });
  } else if (msg.type === "error") {
    update({ error: String(msg["message"] ?? "Unknown interview error") });
  } else if (msg.type === "noise_comparison") {
    update({
      noiseComparison: {
        status: String(msg["status"] ?? "unknown"),
        question_number:
          typeof msg["question_number"] === "number" ? msg["question_number"] : undefined,
        raw_transcript:
          typeof msg["raw_transcript"] === "string" ? msg["raw_transcript"] : undefined,
        filtered_transcript:
          typeof msg["filtered_transcript"] === "string" ? msg["filtered_transcript"] : undefined,
        exact_match: typeof msg["exact_match"] === "boolean" ? msg["exact_match"] : undefined,
        enhancement_ms:
          typeof msg["enhancement_ms"] === "number" ? msg["enhancement_ms"] : undefined,
        provider_latency_ms:
          typeof msg["provider_latency_ms"] === "number" ? msg["provider_latency_ms"] : undefined,
        note: typeof msg["note"] === "string" ? msg["note"] : undefined,
        reason: typeof msg["reason"] === "string" ? msg["reason"] : undefined,
      },
    });
  }
}

export async function startRealtime(setup: SetupDraft): Promise<string> {
  if (client) throw new Error("An interview is already in progress.");
  await loadClient();
  if (!window.RealtimeInterviewClient) throw new Error("Audio client did not load.");
  const next = new window.RealtimeInterviewClient();
  client = next;
  state = initial;
  notify();
  for (const type of ["session_ack", "turn_state", "transcript", "error", "noise_comparison"])
    next.addEventListener(type, handle);
  audioProcessingListener = (event: Event) => {
    const detail = (event as CustomEvent<RealtimeState["audioProcessing"]>).detail;
    if (detail) update({ audioProcessing: detail });
  };
  next.addEventListener("audio-processing", audioProcessingListener);
  next.addEventListener("disconnected", () => update({ connected: false, status: "Disconnected" }));
  try {
    next.preparePlayback();
    const statusResponse = await fetch("/api/status");
    if (!statusResponse.ok) throw new Error("Interview backend is unavailable.");
    const status = (await statusResponse.json()) as { gnani_live?: boolean };
    if (!status.gnani_live)
      throw new Error("Gnani STT/TTS credentials are not configured on the backend.");
    const sessionId = await next.connect({
      track: trackForDomain(setup.domainId),
      language: setup.languageCode,
      consent: true,
      stt_model: "prisma-v2.5",
      endpointing_policy: "adaptive",
      target_questions: setup.questionTarget || 3,
      require_streaming: true,
      noise_eval_enabled: setup.compareNoiseEnhancement === true,
      role: setup.targetRole || "Software Engineer",
      github_repo: setup.github || null,
      resume_text: setup.highlights || null,
    });
    update({ status: "Allow microphone access" });
    void next
      .startCapture()
      .then(() => {
        if (client === next && next.connected) update({ captureReady: true });
      })
      .catch((cause: unknown) => {
        if (client !== next) return;
        update({
          error: cause instanceof Error ? cause.message : String(cause),
          captureReady: false,
        });
        if (audioProcessingListener)
          next.removeEventListener("audio-processing", audioProcessingListener);
        audioProcessingListener = null;
        next.disconnect();
        client = null;
      });
    return sessionId;
  } catch (error) {
    if (audioProcessingListener)
      next.removeEventListener("audio-processing", audioProcessingListener);
    audioProcessingListener = null;
    next.disconnect();
    client = null;
    throw error;
  }
}

export function preloadRealtimeClient() {
  void loadClient();
}

export function endRealtime() {
  client?.endInterview();
}
export function disconnectRealtime() {
  if (client && audioProcessingListener)
    client.removeEventListener("audio-processing", audioProcessingListener);
  audioProcessingListener = null;
  client?.disconnect();
  client = null;
}
export function trackForDomain(id: string): string {
  return (
    ({ software_eng: "software", ai_ml: "ai", agentic_ai: "agentic" } as Record<string, string>)[
      id
    ] ?? "software"
  );
}
