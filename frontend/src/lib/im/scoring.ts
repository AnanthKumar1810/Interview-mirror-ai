import { format } from "date-fns";
import { BACKEND_QUESTIONS, QUESTION_BANK, getDomain, getLanguage } from "./data";
import type { LangCode, LiveInterview, Question, Session, SessionStatus, Turn } from "./types";

/** Words from a concept name that count as evidence when spoken (longer than 3 letters). */
export function conceptKeywords(concept: string): string[] {
  return concept
    .toLowerCase()
    .split(/[\s/()_,.-]+/)
    .filter((w) => w.length > 3);
}

export function isConceptCovered(concept: string, answer: string): boolean {
  const text = answer.toLowerCase();
  if (text.trim().length < 15) return false;
  return conceptKeywords(concept).some((kw) => text.includes(kw));
}

export function coverage(concepts: string[], answer: string) {
  const matched = concepts.filter((c) => isConceptCovered(c, answer));
  const missing = concepts.filter((c) => !matched.includes(c));
  return { matched, missing };
}

/** Practice score for one answer: 62 with no key ideas, up to 92 with all, clamped to 58–96. */
export function scoreAnswer(concepts: string[], answer: string): number {
  const { matched } = coverage(concepts, answer);
  const ratio = concepts.length > 0 ? matched.length / concepts.length : 0.75;
  return Math.min(96, Math.max(58, Math.round(62 + ratio * 30)));
}

export function evaluateTurn(
  q: Pick<Question, "topic" | "expectedConcepts">,
  questionText: string,
  answer: string,
  turnIndex: number,
): Turn {
  const { matched, missing } = coverage(q.expectedConcepts, answer);
  return {
    turnIndex,
    topic: q.topic,
    question: questionText,
    rawTranscript: answer,
    correctedTranscript: answer,
    score: scoreAnswer(q.expectedConcepts, answer),
    evidence:
      matched.length > 0
        ? `Covered: ${matched.join(", ")}.`
        : "Gave a starting explanation — add the specific mechanisms behind it.",
    missingConcepts: missing,
    recommendation:
      missing.length > 0
        ? `Expand on ${missing.join(" and ")} with concrete trade-offs.`
        : "Clear, well-structured answer covering the key ideas.",
    concepts: q.expectedConcepts,
  };
}

/** Find the key ideas for a turn (stored on new turns, looked up by topic for older ones). */
export function conceptsForTurn(turn: Turn): string[] {
  if (turn.concepts?.length) return turn.concepts;
  for (const pool of Object.values(QUESTION_BANK)) {
    const q = pool?.find((x) => x.topic === turn.topic);
    if (q) return q.expectedConcepts;
  }
  return [];
}

export function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
}

export function averageScore(turns: Turn[]): number {
  if (turns.length === 0) return 0;
  return Math.round(turns.reduce((a, t) => a + t.score, 0) / turns.length);
}

export function dimensionsFor(avg: number) {
  return {
    technicalAccuracy: Math.min(95, avg + 3),
    designTradeoffs: Math.max(55, avg - 2),
    projectUnderstanding: avg,
    communicationClarity: Math.min(94, avg + 1),
  };
}

export function buildSession(live: LiveInterview, now = new Date()): Session {
  const { setup } = live;
  const domain = getDomain(setup.domainId);
  const lang = getLanguage(setup.languageCode);
  const turns = live.turns;
  const avg = averageScore(turns);
  const status: SessionStatus = turns.length >= live.questions.length ? "Completed" : "Partial";
  const seconds = Math.max(30, Math.round((now.getTime() - live.startedAt) / 1000));
  const improvements = turns
    .flatMap((t) => t.missingConcepts)
    .slice(0, 3)
    .map((c) => `Go deeper on: ${c}`);

  return {
    id: live.id,
    domainId: domain.id,
    domainName: domain.name,
    targetRole: setup.targetRole || "Software Engineer",
    languageCode: lang.code,
    languageLabel: lang.native,
    difficulty: setup.difficulty,
    questionTarget: live.questions.length,
    questionsCompleted: turns.length,
    date: format(now, "yyyy-MM-dd HH:mm"),
    durationSeconds: seconds,
    durationFormatted: formatDuration(seconds),
    status,
    overallScore: avg,
    dimensions: dimensionsFor(avg),
    strengths: turns
      .filter((t) => t.missingConcepts.length < (t.concepts?.length ?? 4))
      .map((t) => {
        const total = t.concepts?.length ?? 0;
        const covered = total - t.missingConcepts.length;
        return `${t.topic} — covered ${covered} of ${total} key ideas.`;
      }),
    improvements:
      improvements.length > 0
        ? improvements
        : ["Keep practising — add numbers (latency, memory, limits) to strengthen answers."],
    roadmap: [
      {
        step: `Review the core ideas in ${turns[0]?.topic ?? domain.name}`,
        detail: turns[0]?.recommendation ?? "Revisit the fundamentals of this track.",
      },
      {
        step: `Practise explaining ${domain.name} trade-offs in ${lang.label}`,
        detail:
          "Connect each design choice to its effect on latency, concurrency and failure handling.",
      },
      {
        step: "Try a 5-question session next",
        detail: "A longer session gives a fuller picture across all four skill areas.",
      },
    ],
    turns,
  };
}

/** Re-score a session after the user corrects a transcript. */
export function applyCorrection(session: Session, turnIdx: number, text: string): Session {
  const turns = session.turns.map((t, i) => {
    if (i !== turnIdx) return t;
    const concepts = conceptsForTurn(t);
    if (concepts.length === 0) return { ...t, correctedTranscript: text };
    const fresh = evaluateTurn(
      { topic: t.topic, expectedConcepts: concepts },
      t.question,
      text,
      t.turnIndex,
    );
    return { ...fresh, rawTranscript: t.rawTranscript, correctedTranscript: text };
  });
  const avg = averageScore(turns);
  return { ...session, turns, overallScore: avg, dimensions: dimensionsFor(avg) };
}

export function questionText(q: Question, lang: LangCode) {
  return q.prompt[lang] || q.prompt["en-IN"];
}

export function pickQuestions(domainId: string, count: number): Question[] {
  const pool = QUESTION_BANK[domainId] ?? BACKEND_QUESTIONS;
  return pool.slice(0, Math.min(count, pool.length));
}

export function scoreTone(score: number): "success" | "info" | "warning" {
  if (score >= 80) return "success";
  if (score >= 70) return "info";
  return "warning";
}
