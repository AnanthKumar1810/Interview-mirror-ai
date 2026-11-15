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
  });
});
