import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Check, Mic, Play, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader, Panel } from "@/components/im/bits";
import { DOMAINS, LANGUAGES, getDomain, getLanguage } from "@/lib/im/data";
import { actions, useAppStore } from "@/lib/im/store";
import type { Difficulty } from "@/lib/im/types";
import { cn } from "@/lib/utils";
import { preloadRealtimeClient, startRealtime } from "@/lib/im/realtime";

export const Route = createFileRoute("/app/new")({
  head: () => ({
    meta: [
      { title: "New interview — InterviewMirror" },
      {
        name: "description",
        content: "Set up a practice interview: choose a track, language, difficulty and length.",
      },
      { property: "og:title", content: "New interview — InterviewMirror" },
      {
        property: "og:description",
        content: "Set up your next technical practice interview in four quick steps.",
      },
    ],
  }),
  component: NewInterview,
});

const STEPS = ["Track", "Language", "Format", "Personalise"] as const;

const DIFFICULTIES: { value: Difficulty; title: string; body: string }[] = [
  { value: "Fundamentals", title: "Fundamentals", body: "Core concepts and definitions" },
  { value: "Intermediate", title: "Intermediate", body: "Concurrency, storage and trade-offs" },
  { value: "Advanced", title: "Advanced", body: "Scale, latency and failure modes" },
];

const LENGTHS = [{ value: 3, title: "Practice", body: "3 questions • up to 10 min" }] as const;

function NewInterview() {
  const setup = useAppStore((s) => s.setup);
  const live = useAppStore((s) => s.live);
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [starting, setStarting] = useState(false);
  useEffect(() => {
    preloadRealtimeClient();
  }, []);

  const domain = getDomain(setup.domainId);
  const lang = getLanguage(setup.languageCode);

  const start = async () => {
    if (starting) return;
    setStarting(true);
    try {
      const sessionId = await startRealtime(setup);
      actions.setLive({
        id: sessionId,
        setup: { ...setup, questionTarget: 3 },
        questions: [],
        index: 0,
        turns: [],
        startedAt: Date.now(),
      });
      await navigate({ to: "/interview" });
    } catch (error) {
      toast.error("Could not start the interview", {
        description: error instanceof Error ? error.message : String(error),
      });
      setStarting(false);
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="New interview"
        title="Set up your practice interview"
        description="Four quick steps. You can start at any time — sensible defaults are already chosen."
      />

      {live && (
        <div className="flex flex-col gap-3 rounded-2xl border border-teal/30 bg-teal-soft p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm">You have an interview in progress.</p>
          <Button size="sm" variant="outline" onClick={() => navigate({ to: "/interview" })}>
            Resume it
          </Button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          {/* Stepper */}
          <ol className="grid grid-cols-4 gap-2">
            {STEPS.map((label, i) => (
              <li key={label}>
                <button
                  onClick={() => setStep(i)}
                  className={cn(
                    "flex w-full flex-col gap-2 rounded-xl p-2 text-left transition-colors hover:bg-card",
                  )}
                >
                  <span
                    className={cn("h-1 rounded-full", i <= step ? "bg-gradient-brand" : "bg-muted")}
                  />
                  <span className="flex items-center gap-2 text-xs font-semibold">
                    <span
                      className={cn(
                        "grid size-5 place-items-center rounded-full text-[10px]",
                        i < step
                          ? "bg-teal text-primary-foreground"
                          : i === step
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground",
                      )}
                    >
                      {i < step ? <Check className="size-3" /> : i + 1}
                    </span>
                    <span
                      className={cn(
                        "hidden sm:inline",
                        i === step ? "text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {label}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>

          <Panel className="animate-fade-up" key={step}>
            {step === 0 && (
              <StepBody
                title="Which role are you preparing for?"
                hint="Questions are tailored to this track."
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  {DOMAINS.map((d) => (
                    <OptionCard
                      key={d.id}
                      selected={d.id === setup.domainId}
                      onClick={() => actions.updateSetup({ domainId: d.id })}
                    >
                      <p className="font-semibold">{d.name}</p>
                      <p className="mt-1 text-xs text-teal">{d.badge}</p>
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                        {d.description}
                      </p>
                    </OptionCard>
                  ))}
                </div>
              </StepBody>
            )}

            {step === 1 && (
              <StepBody
                title="Which language do you want to speak?"
                hint="Technical terms can always stay in English."
              >
                <div className="grid gap-3">
                  {LANGUAGES.map((l) => (
                    <OptionCard
                      key={l.code}
                      selected={l.code === setup.languageCode}
                      onClick={() => actions.updateSetup({ languageCode: l.code })}
                    >
                      <p className="font-semibold">{l.native}</p>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                        {l.guidance}
                      </p>
                    </OptionCard>
                  ))}
                </div>
              </StepBody>
            )}

            {step === 2 && (
              <StepBody
                title="Interview format"
                hint="The current live backend asks three adaptive questions."
              >
                <Label className="mb-3 block text-xs text-muted-foreground">Length</Label>
                <div className="grid gap-3 sm:grid-cols-3">
                  {LENGTHS.map((l) => (
                    <OptionCard
                      key={l.value}
                      selected={setup.questionTarget === l.value}
                      onClick={() => actions.updateSetup({ questionTarget: l.value })}
                    >
                      <p className="font-semibold">{l.title}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{l.body}</p>
                    </OptionCard>
                  ))}
                </div>
              </StepBody>
            )}

            {step === 3 && <PersonaliseStep />}

            <div className="mt-8 flex items-center justify-between border-t border-border pt-5">
              <Button
                variant="ghost"
                onClick={() => setStep((s) => Math.max(0, s - 1))}
                disabled={step === 0}
              >
                <ArrowLeft /> Back
              </Button>
              {step < STEPS.length - 1 ? (
                <Button onClick={() => setStep((s) => s + 1)}>
                  Continue <ArrowRight />
                </Button>
              ) : (
                <Button variant="hero" onClick={start} disabled={starting}>
                  <Play /> {starting ? "Connecting…" : "Start interview"}
                </Button>
              )}
            </div>
          </Panel>
        </div>

        {/* Summary */}
        <aside className="lg:sticky lg:top-8 lg:self-start">
          <Panel>
            <p className="eyebrow mb-4">Your interview</p>
            <dl className="space-y-3 text-sm">
              {[
                ["Track", domain.name],
                ["Language", lang.label],
                ["Length", "3 questions"],
                ["Role", setup.targetRole || "—"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="truncate text-right font-medium">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-5 rounded-xl border border-border bg-elevated/50 p-4">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-primary">
                Opening question
              </p>
              <p className="text-sm leading-relaxed">
                The live interviewer opens with an introduction, then selects follow-up questions
                based on your answers.
              </p>
            </div>
            <Button
              variant="hero"
              size="lg"
              className="mt-5 w-full"
              onClick={start}
              disabled={starting}
            >
              <Play /> {starting ? "Connecting…" : "Start interview"}
            </Button>
            <p className="mt-3 text-center text-xs text-muted-foreground">
              Your microphone audio is streamed to Gnani for speech recognition. Start grants audio
              consent.
            </p>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

function StepBody({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mb-6 mt-1 text-sm text-muted-foreground">{hint}</p>
      {children}
    </div>
  );
}

function OptionCard({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "relative w-full rounded-xl border p-4 text-left transition-all",
        selected
          ? "border-primary bg-primary-soft shadow-glow"
          : "border-border bg-background/40 hover:border-primary/40 hover:bg-elevated/60",
      )}
    >
      {selected && (
        <span className="absolute right-3 top-3 grid size-5 place-items-center rounded-full bg-primary text-primary-foreground">
          <Check className="size-3" />
        </span>
      )}
      {children}
    </button>
  );
}

function PersonaliseStep() {
  const setup = useAppStore((s) => s.setup);
  const fileRef = useRef<HTMLInputElement>(null);

  const onFile = (file?: File) => {
    if (!file) return;
    if (!/\.(txt|md)$/i.test(file.name)) {
      toast.error("Please upload a .txt or .md file");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      actions.updateSetup({
        highlights: String(reader.result ?? "")
          .slice(0, 1200)
          .trim(),
      });
      toast.success("Resume highlights added");
    };
    reader.readAsText(file);
  };

  return (
    <StepBody
      title="Make it about you (optional)"
      hint="This helps follow-up questions focus on your real projects."
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="role">Target role</Label>
          <Input
            id="role"
            value={setup.targetRole}
            onChange={(e) => actions.updateSetup({ targetRole: e.target.value })}
            placeholder="e.g. Backend Engineer"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="gh">GitHub (optional)</Label>
          <Input
            id="gh"
            value={setup.github}
            onChange={(e) => actions.updateSetup({ github: e.target.value })}
            placeholder="github.com/you/project"
          />
        </div>
      </div>
      <div className="mt-5 space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="hl">Project & resume highlights</Label>
          <button
            onClick={() => fileRef.current?.click()}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
          >
            <Upload className="size-3.5" /> Upload .txt / .md
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md"
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
        </div>
        <Textarea
          id="hl"
          rows={4}
          value={setup.highlights}
          onChange={(e) => actions.updateSetup({ highlights: e.target.value })}
          placeholder="e.g. Built a FastAPI streaming service with SQLite persistence…"
        />
      </div>
      <MicCheck />
    </StepBody>
  );
}

function MicCheck() {
  const [status, setStatus] = useState<"idle" | "testing" | "ok" | "denied">("idle");
  const [level, setLevel] = useState(0);
  const cleanup = useRef<() => void>(() => {});

  useEffect(() => () => cleanup.current(), []);

  const test = async () => {
    try {
      setStatus("testing");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      ctx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      let raf = 0;
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        setLevel(Math.min(100, avg * 1.6));
        raf = requestAnimationFrame(tick);
      };
      tick();
      cleanup.current = () => {
        cancelAnimationFrame(raf);
        stream.getTracks().forEach((t) => t.stop());
        ctx.close();
      };
      setTimeout(() => {
        cleanup.current();
        setLevel(0);
        setStatus("ok");
      }, 5000);
    } catch {
      setStatus("denied");
    }
  };

  return (
    <div className="mt-6 flex flex-col gap-4 rounded-xl border border-border bg-background/40 p-4 sm:flex-row sm:items-center">
      <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-soft text-teal">
        <Mic className="size-5" />
      </div>
      <div className="flex-1">
        <p className="text-sm font-semibold">Microphone check</p>
        <p className="text-xs text-muted-foreground">
          {status === "idle" && "Optional check before you start."}
          {status === "testing" && "Say something… we're listening for 5 seconds."}
          {status === "ok" && "Your microphone works."}
          {status === "denied" && "Microphone blocked. Allow microphone access in your browser."}
        </p>
        {status === "testing" && (
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-teal transition-[width] duration-75"
              style={{ width: `${level}%` }}
            />
          </div>
        )}
      </div>
      {status === "ok" ? (
        <Badge variant="success" className="gap-1">
          <Check className="size-3" /> Ready
        </Badge>
      ) : (
        <Button size="sm" variant="outline" onClick={test} disabled={status === "testing"}>
          Test microphone
        </Button>
      )}
    </div>
  );
}
