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
};
let state = initial;
let client: Client | null = null;
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
  for (const type of ["session_ack", "turn_state", "transcript", "error"])
    next.addEventListener(type, handle);
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
      target_questions: 3,
      require_streaming: true,
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
        next.disconnect();
        client = null;
      });
    return sessionId;
  } catch (error) {
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
