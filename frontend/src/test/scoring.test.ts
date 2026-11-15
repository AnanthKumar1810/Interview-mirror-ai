import { describe, expect, it } from "vitest";
import { applyCorrection, buildSession, scoreAnswer } from "@/lib/im/scoring";
import { BACKEND_QUESTIONS, SEEDED_SESSIONS } from "@/lib/im/data";
import type { Session, Turn } from "@/lib/im/types";

const seed = SEEDED_SESSIONS[0] as Session;

const concepts = ["Bounded queue capacity", "Monotonic turn identifiers"];

describe("practice scoring", () => {
  it("gives 62 when no key ideas are mentioned", () => {
    expect(scoreAnswer(concepts, "I would just make it faster somehow, honestly.")).toBe(62);
  });

  it("gives 92 when every key idea is mentioned", () => {
    expect(
      scoreAnswer(concepts, "Use a bounded queue and a monotonic turn id for each reply."),
    ).toBe(92);
  });

  it("marks a session Partial when not every question was answered", () => {
    const qs = BACKEND_QUESTIONS.slice(0, 3);
    const s = buildSession({
      id: "t1",
      setup: {
        domainId: "backend_eng",
        languageCode: "en-IN",
        difficulty: "Intermediate",
        questionTarget: 3,
        targetRole: "Dev",
        github: "",
        highlights: "",
      },
      questions: qs,
      index: 1,
      turns: [{ ...(seed.turns[0] as Turn), score: 80 }],
      startedAt: Date.now() - 60000,
    });
    expect(s.status).toBe("Partial");
    expect(s.overallScore).toBe(80);
  });

  it("re-scores a session after a transcript correction", () => {
    const updated = applyCorrection(seed, 2, "short");
    expect(updated.turns[2]?.score).toBe(62);
    expect(updated.overallScore).toBe(Math.round((84 + 78 + 62) / 3));
  });
});
