import { describe, expect, it } from "vitest";
import { getRealtimeState, receiveRealtimeMessage } from "@/lib/im/realtime";

describe("realtime interview control events", () => {
  it("shows a partial transcript and advances after server feedback", () => {
    receiveRealtimeMessage({
      type: "session_ack",
      session_id: "test-session",
      question: "Introduce yourself",
      question_number: 1,
      total_questions: 3,
    });
    receiveRealtimeMessage({
      type: "turn_state",
      state: "Listening to your answer",
      raw_state: "listening",
      question: "Introduce yourself",
      question_number: 1,
    });
    receiveRealtimeMessage({ type: "transcript", text: "I built", is_final: false });
    expect(getRealtimeState().transcript).toBe("I built");
    receiveRealtimeMessage({
      type: "transcript",
      text: "I built a service",
      is_final: true,
      is_turn_final: true,
    });
    receiveRealtimeMessage({
      type: "turn_state",
      state: "Evaluating feedback",
      raw_state: "feedback",
      question: "How did you test it?",
      question_number: 2,
      feedback: { score: 72 },
    });
    expect(getRealtimeState()).toMatchObject({
      question: "How did you test it?",
      questionNumber: 2,
      transcript: "",
    });
    expect(getRealtimeState().turns).toMatchObject([
      { question: "Introduce yourself", transcript: "I built a service" },
    ]);
    receiveRealtimeMessage({
      type: "noise_comparison",
      status: "complete",
      question_number: 1,
      raw_transcript: "I built a service",
      filtered_transcript: "I built service",
      exact_match: false,
      enhancement_ms: 13,
      provider_latency_ms: 1800,
      note: "Transcript comparison only.",
    });
    expect(getRealtimeState().noiseComparison).toMatchObject({
      status: "complete",
      question_number: 1,
      exact_match: false,
      provider_latency_ms: 1800,
    });
  });

  it("ignores stale RTC transcripts and turn states after advancing", () => {
    receiveRealtimeMessage({
      type: "session_ack",
      session_id: "test-session",
      question: "First",
      question_number: 1,
    });
    receiveRealtimeMessage({
      type: "turn_state",
      state: "Listening",
      raw_state: "listening",
      question: "Second",
      question_number: 2,
    });
    receiveRealtimeMessage({ type: "transcript", text: "old audio", question_number: 1 });
    receiveRealtimeMessage({
      type: "turn_state",
      state: "Listening",
      raw_state: "listening",
      question: "First",
      question_number: 1,
    });
    expect(getRealtimeState().question).toBe("Second");
    expect(getRealtimeState().transcript).not.toBe("old audio");
  });
});
