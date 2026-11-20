export type LangCode = "en-IN" | "te-IN" | "hi-IN";
export type Difficulty = "Fundamentals" | "Intermediate" | "Advanced";
export type SessionStatus = "Completed" | "Partial";

export interface Domain {
  id: string;
  name: string;
  badge: string;
  description: string;
  competencies: string[];
}

export interface Language {
  code: LangCode;
  label: string;
  native: string;
  guidance: string;
}

export interface Question {
  id: string;
  topic: string;
  difficulty: Difficulty;
  prompt: Record<LangCode, string>;
  expectedConcepts: string[];
  sampleAnswers: Record<LangCode, string>;
}

export interface Turn {
  turnIndex: number;
  topic: string;
  question: string;
  rawTranscript: string;
  correctedTranscript: string;
  score: number;
  evidence: string;
  missingConcepts: string[];
  recommendation: string;
  concepts?: string[];
}

export interface Dimensions {
  technicalAccuracy: number;
  designTradeoffs: number;
  projectUnderstanding: number;
  communicationClarity: number;
}

export interface Session {
  id: string;
  domainId: string;
  domainName: string;
  targetRole: string;
  languageCode: LangCode;
  languageLabel: string;
  difficulty: Difficulty;
  questionTarget: number;
  questionsCompleted: number;
  date: string;
  durationSeconds: number;
  durationFormatted: string;
  status: SessionStatus;
  overallScore: number;
  dimensions: Dimensions;
  strengths: string[];
  improvements: string[];
  roadmap: { step: string; detail: string }[];
  turns: Turn[];
}

export interface SetupDraft {
  domainId: string;
  languageCode: LangCode;
  difficulty: Difficulty;
  questionTarget: 3 | 5 | 7;
  targetRole: string;
  github: string;
  highlights: string;
  useGemini?: boolean;
  compareNoiseEnhancement?: boolean;
  voiceTransport?: "websocket" | "livekit";
}

export interface Profile {
  name: string;
  targetRole: string;
  language: LangCode;
  speakQuestions: boolean;
}

export interface LiveInterview {
  id: string;
  setup: SetupDraft;
  questions: Question[];
  index: number;
  turns: Turn[];
  startedAt: number;
}
