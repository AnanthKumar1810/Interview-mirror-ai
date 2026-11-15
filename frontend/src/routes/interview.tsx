import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Clock, Loader2, Mic, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { VoiceOrb, type OrbState } from "@/components/im/VoiceOrb";
import { formatDuration } from "@/lib/im/scoring";
import { actions, useAppStore } from "@/lib/im/store";
import { disconnectRealtime, endRealtime, useRealtimeState } from "@/lib/im/realtime";
import { getDomain } from "@/lib/im/data";

export const Route = createFileRoute("/interview")({ component: InterviewPage });

function InterviewPage() {
  const live = useAppStore((s) => s.live);
  const hydrated = useAppStore((s) => s.hydrated);
  const realtime = useRealtimeState();
  const navigate = useNavigate();
  const [elapsed, setElapsed] = useState(0);
  const [ending, setEnding] = useState(false);

  useEffect(() => {
    if (hydrated && !live) void navigate({ to: "/app/new", replace: true });
  }, [hydrated, live, navigate]);
  useEffect(() => {
    if (!live) return;
    const tick = () => setElapsed(Math.floor((Date.now() - live.startedAt) / 1000));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [live]);

  const finish = async () => {
    if (!live || ending) return;
    setEnding(true);
    endRealtime();
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    disconnectRealtime();
    await navigate({ to: "/app/report/$id", params: { id: live.id } });
    actions.setLive(null);
  };

  useEffect(() => {
    if (live && realtime.rawState === "completed" && !ending) void finish();
  }, [live, realtime.rawState, ending]);

  if (!live)
    return (
      <div className="grid min-h-screen place-items-center">
        <Loader2 className="animate-spin" />
      </div>
    );
  const orb: OrbState =
    realtime.rawState === "asking"
      ? "speaking"
      : realtime.rawState === "listening"
        ? "listening"
        : realtime.rawState === "completed"
          ? "idle"
          : "thinking";

  return (
    <div className="flex min-h-screen flex-col bg-gradient-hero">
      <header className="border-b border-border/60 bg-background/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-center gap-4">
            <span className="font-display font-semibold">InterviewMirror</span>
            <div>
              <p className="text-sm font-semibold">{getDomain(live.setup.domainId).name}</p>
              <p className="text-xs text-muted-foreground">
                Question {Math.min(realtime.questionNumber, realtime.totalQuestions)} of{" "}
                {realtime.totalQuestions}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="muted" className="gap-1.5 tabular-nums">
              <Clock className="size-3" /> {formatDuration(elapsed)}
            </Badge>
            <Button variant="outline" size="sm" onClick={() => void finish()} disabled={ending}>
              <X /> End
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto grid w-full max-w-5xl flex-1 gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[1fr_280px]">
        <div className="space-y-6">
          <section className="surface p-6 sm:p-8">
            <div className="flex flex-col items-center text-center">
              <VoiceOrb state={orb} size={150} />
              <p className="mt-4 text-lg font-semibold">{realtime.status}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {realtime.captureReady
                  ? "Microphone streaming to Gnani"
                  : realtime.connected
                    ? "Allow microphone access in your browser to answer"
                    : "Connection closed"}
              </p>
            </div>
            <div className="mt-8 rounded-2xl border border-border bg-elevated/50 p-5">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-primary">
                Current question
              </p>
              <p className="text-base leading-relaxed sm:text-lg">
                {realtime.question || "Preparing your interview…"}
              </p>
            </div>
          </section>
          <section className="surface p-5 sm:p-6">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Mic className="size-4 text-teal" /> Live transcript
            </h2>
            <p className="mt-3 min-h-24 whitespace-pre-wrap rounded-xl bg-background/60 p-4 text-sm leading-relaxed">
              {realtime.transcript ||
                "Speak naturally after the question. Your answer is submitted automatically when you stop speaking."}
            </p>
            {realtime.audioProcessing && (
              <p className="mt-3 text-xs text-muted-foreground" aria-live="polite">
                Browser noise suppression:{" "}
                {realtime.audioProcessing.noiseSuppression === true
                  ? "enabled"
                  : realtime.audioProcessing.noiseSuppression === false
                    ? "not enabled"
                    : "not reported by this browser"}
                . Echo cancellation:{" "}
                {realtime.audioProcessing.echoCancellation === true
                  ? "enabled"
                  : realtime.audioProcessing.echoCancellation === false
                    ? "not enabled"
                    : "not reported"}
                . These browser settings do not guarantee noise removal or improved transcription.
              </p>
            )}
            <p className="mt-3 text-xs text-muted-foreground">
              Transcription and voice use Gnani Prisma and Timbre. Feedback is a transcript-based
              practice indicator.
            </p>
          </section>
          {realtime.noiseComparison && (
            <section className="surface p-5 sm:p-6" aria-live="polite">
              <h2 className="text-sm font-semibold">
                Experimental noise-filter comparison
                {realtime.noiseComparison.question_number
                  ? ` · Question ${realtime.noiseComparison.question_number}`
                  : ""}
              </h2>
              {realtime.noiseComparison.status === "complete" ? (
                <>
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Live Prisma transcript
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-sm">
                        {realtime.noiseComparison.raw_transcript}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Filtered second-pass transcript
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-sm">
                        {realtime.noiseComparison.filtered_transcript}
                      </p>
                    </div>
                  </div>
                  <p className="mt-4 text-xs text-muted-foreground">
                    Filter time: {realtime.noiseComparison.enhancement_ms} ms; additional Prisma
                    request: {realtime.noiseComparison.provider_latency_ms} ms. Exact text match:{" "}
                    {realtime.noiseComparison.exact_match ? "yes" : "no"}. This is a transcript
                    comparison, not an accuracy score.
                  </p>
                  {realtime.noiseComparison.note && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {realtime.noiseComparison.note}
                    </p>
                  )}
                </>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  {realtime.noiseComparison.reason ?? "Comparison did not complete."}
                </p>
              )}
            </section>
          )}
          {realtime.error && (
            <div
              role="alert"
              className="rounded-xl border border-destructive/50 bg-destructive/10 p-4 text-sm"
            >
              {realtime.error}
            </div>
          )}
        </div>
        <aside className="space-y-6">
          <section className="surface p-5">
            <h2 className="text-sm font-semibold">Answered</h2>
            {realtime.turns.length ? (
              <ol className="mt-4 space-y-3 text-sm">
                {realtime.turns.map((turn, index) => (
                  <li key={index} className="border-b border-border pb-3">
                    <p className="font-medium">
                      {index + 1}. {turn.question}
                    </p>
                    <p className="mt-1 line-clamp-2 text-muted-foreground">{turn.transcript}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">
                Your completed answers will appear here.
              </p>
            )}
          </section>
          <p className="px-1 text-xs text-muted-foreground">
            The interviewer advances after a detected pause. You can interrupt its voice by
            speaking.
          </p>
        </aside>
      </main>
    </div>
  );
}
