import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Panel, PageHeader } from "@/components/im/bits";
import { actions, useAppStore } from "@/lib/im/store";
import { getDomain, getLanguage } from "@/lib/im/data";
import { formatDuration } from "@/lib/im/scoring";
import type { LangCode, Session, Turn } from "@/lib/im/types";

export const Route = createFileRoute("/app/report/$id")({ component: ReportPage });

interface AnswerRecord {
  question: string;
  transcript: string;
  provider_transcript?: string;
  edited_transcript?: string;
  feedback: {
    score?: number;
    dimensions?: Record<string, number>;
    evidence_items?: { quote?: string; observation?: string }[];
    missing_concepts?: string[];
    improvements?: string[];
    factual_assessment?: string;
    method?: string;
  };
}
interface BackendReport {
  session_id: string;
  created: string;
  track: string;
  language: string;
  answered: number;
  total_questions: number;
  average_score: number | null;
  dimension_averages: Record<string, number>;
  review_priorities: string[];
  results: AnswerRecord[];
  method: string;
  note: string;
}

function ReportPage() {
  const { id } = Route.useParams();
  const live = useAppStore((s) => s.live);
  const setup = useAppStore((s) => s.setup);
  const currentContext = useRef({ live, setup });
  currentContext.current = { live, setup };
  const [report, setReport] = useState<BackendReport | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetch(`/api/report/${encodeURIComponent(id)}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            response.status === 404
              ? "This report was not found or has expired."
              : "Could not load the report.",
          );
        return response.json() as Promise<BackendReport>;
      })
      .then((data) => {
        if (!active) return;
        const { live: currentLive, setup: currentSetup } = currentContext.current;
        setReport(data);
        const domainId =
          (
            {
              "Agentic AI": "agentic_ai",
              "Machine Learning": "ai_ml",
              "Software Engineering": "software_eng",
            } as Record<string, string>
          )[data.track] ?? currentSetup.domainId;
        const languageCode: LangCode =
          ({ Telugu: "te-IN", Hindi: "hi-IN", English: "en-IN" } as Record<string, LangCode>)[
            data.language
          ] ?? currentSetup.languageCode;
        const turns: Turn[] = data.results.map((answer, index) => ({
          turnIndex: index + 1,
          topic: `Question ${index + 1}`,
          question: answer.question,
          rawTranscript: answer.provider_transcript || answer.transcript,
          correctedTranscript: answer.edited_transcript || answer.transcript,
          score: answer.feedback.score ?? 0,
          evidence:
            answer.feedback.evidence_items
              ?.map((item) => item.observation || item.quote)
              .filter(Boolean)
              .join(" ") || "Evidence was not supplied.",
          missingConcepts: answer.feedback.missing_concepts || [],
          recommendation:
            answer.feedback.improvements?.[0] || "Review your answer against the question.",
        }));
        const session: Session = {
          id,
          domainId,
          domainName: getDomain(domainId).name,
          targetRole: currentSetup.targetRole || "Candidate",
          languageCode,
          languageLabel: getLanguage(languageCode).label,
          difficulty: currentSetup.difficulty || "Intermediate",
          questionTarget: data.total_questions,
          questionsCompleted: data.answered,
          date: new Date(data.created).toLocaleString(),
          durationSeconds: currentLive
            ? Math.round((Date.now() - currentLive.startedAt) / 1000)
            : 0,
          durationFormatted: currentLive
            ? formatDuration(Math.round((Date.now() - currentLive.startedAt) / 1000))
            : "—",
          status: data.answered >= data.total_questions ? "Completed" : "Partial",
          overallScore: data.average_score ?? 0,
          dimensions: {
            technicalAccuracy: Math.round(
              ((data.dimension_averages["technical_coverage"] || 0) / 35) * 100,
            ),
            designTradeoffs: Math.round(((data.dimension_averages["evidence"] || 0) / 20) * 100),
            projectUnderstanding: Math.round(
              ((data.dimension_averages["relevance"] || 0) / 25) * 100,
            ),
            communicationClarity: Math.round(
              ((data.dimension_averages["clarity"] || 0) / 20) * 100,
            ),
          },
          strengths: [],
          improvements: data.review_priorities.map((x) => `Review: ${x}`),
          roadmap: data.review_priorities.slice(0, 3).map((x) => ({
            step: `Review ${x}`,
            detail:
              "Check the concept with a trusted technical reference and practise explaining it.",
          })),
          turns,
        };
        actions.saveSession(session);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (error)
    return (
      <div className="space-y-4 py-16">
        <p role="alert">{error}</p>
        <Button asChild>
          <Link to="/app/history">History</Link>
        </Button>
      </div>
    );
  if (!report)
    return (
      <div className="grid place-items-center py-24">
        <Loader2 className="animate-spin" />
      </div>
    );
  return (
    <div className="space-y-6">
      <Link
        to="/app/history"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground"
      >
        <ArrowLeft className="size-4" /> All interviews
      </Link>
      <PageHeader
        eyebrow="Practice report"
        title={report.track}
        description={`${report.answered} of ${report.total_questions} questions answered • ${report.language}`}
      />
      <Panel>
        <p className="text-4xl font-semibold">
          {report.average_score ?? "—"}
          <span className="text-base text-muted-foreground"> / 100 practice score</span>
        </p>
        <p className="mt-3 text-sm text-muted-foreground">{report.note}</p>
      </Panel>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(report.dimension_averages).map(([name, value]) => (
          <Panel key={name}>
            <p className="text-xs text-muted-foreground">{name.replaceAll("_", " ")}</p>
            <p className="mt-2 text-xl font-semibold">
              {value} /{" "}
              {{ relevance: 25, technical_coverage: 35, clarity: 20, evidence: 20 }[name] ?? 100}
            </p>
          </Panel>
        ))}
      </div>
      {report.review_priorities.length > 0 && (
        <Panel>
          <h2 className="flex items-center gap-2 font-semibold">
            <Target className="size-4" /> Review priorities
          </h2>
          <ul className="mt-3 list-inside list-disc space-y-1 text-sm">
            {report.review_priorities.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Panel>
      )}
      <div className="space-y-4">
        {report.results.map((answer, index) => (
          <Panel key={index}>
            <div className="flex items-start justify-between gap-4">
              <h2 className="font-semibold">
                {index + 1}. {answer.question}
              </h2>
              <span className="shrink-0 text-sm">{answer.feedback.score ?? "—"}/100</span>
            </div>
            <p className="mt-4 text-xs uppercase tracking-wider text-primary">Gnani transcript</p>
            <p className="mt-1 whitespace-pre-wrap text-sm">
              {answer.provider_transcript || answer.transcript}
            </p>
            {answer.edited_transcript && (
              <p className="mt-2 text-xs text-muted-foreground">
                Corrected: {answer.edited_transcript}
              </p>
            )}
            {answer.feedback.evidence_items?.length ? (
              <div className="mt-4 space-y-2 text-sm">
                {answer.feedback.evidence_items.map((item, itemIndex) => (
                  <p key={itemIndex} className="rounded-lg bg-elevated p-3">
                    {item.quote && <span className="font-medium">“{item.quote}” </span>}
                    {item.observation}
                  </p>
                ))}
              </div>
            ) : null}
            {answer.feedback.improvements?.length ? (
              <ul className="mt-4 list-inside list-disc text-sm text-muted-foreground">
                {answer.feedback.improvements.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
            <p className="mt-3 text-xs text-muted-foreground">
              Method: {answer.feedback.method || report.method}; factual verification:{" "}
              {answer.feedback.factual_assessment || "not verified"}
            </p>
          </Panel>
        ))}
      </div>
    </div>
  );
}
