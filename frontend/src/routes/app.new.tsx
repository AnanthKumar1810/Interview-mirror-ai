import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  FileText,
  Github,
  Mic,
  Play,
  Sparkles,
  Upload,
} from "lucide-react";
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

const LENGTHS: {
  value: 3 | 5 | 7;
  title: string;
  subtitle: string;
  body: string;
  badge?: string;
}[] = [
  {
    value: 3,
    title: "Quick Practice",
    subtitle: "3 questions • ~10 min",
    body: "Rapid technical warm-up focusing on core role fundamentals and adaptive follow-up.",
    badge: "Fastest",
  },
  {
    value: 5,
    title: "Full Mock Interview",
    subtitle: "5 questions • ~20 min",
    body: "Standard technical interview covering architecture trade-offs, debugging, and resume projects.",
    badge: "Recommended",
  },
  {
    value: 7,
    title: "In-Depth Architectural",
    subtitle: "7 questions • ~35 min",
    body: "Comprehensive drill-down with edge cases, failure modes, scale, and system boundaries.",
  },
];

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
        setup: { ...setup, questionTarget: setup.questionTarget || 3 },
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
                hint="Choose your session length and evaluation depth."
              >
                <Label className="mb-3 block text-xs text-muted-foreground">Length & Scope</Label>
                <div className="grid gap-3 sm:grid-cols-3">
                  {LENGTHS.map((l) => (
                    <OptionCard
                      key={l.value}
                      selected={(setup.questionTarget || 3) === l.value}
                      onClick={() =>
                        actions.updateSetup({
                          questionTarget: l.value,
                          voiceTransport:
                            l.value === 3 ? (setup.voiceTransport ?? "websocket") : "websocket",
                        })
                      }
                    >
                      <div className="flex items-center justify-between">
                        <p className="font-semibold">{l.title}</p>
                        {l.badge && (
                          <Badge variant="outline" className="border-teal/30 text-[10px] text-teal">
                            {l.badge}
                          </Badge>
                        )}
                      </div>
                      <p className="mt-1 text-xs font-medium text-teal">{l.subtitle}</p>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{l.body}</p>
                    </OptionCard>
                  ))}
                </div>
                <div className="mt-5 rounded-xl border border-border bg-background/40 p-4">
                  <Label className="mb-3 block text-sm font-medium">Voice connection</Label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <OptionCard
                      selected={setup.voiceTransport !== "livekit"}
                      onClick={() => actions.updateSetup({ voiceTransport: "websocket" })}
                    >
                      <span className="text-sm font-medium">Standard voice</span>
                    </OptionCard>
                    <OptionCard
                      selected={setup.voiceTransport === "livekit"}
                      onClick={() =>
                        actions.updateSetup({
                          voiceTransport: "livekit",
                          questionTarget: 3,
                          compareNoiseEnhancement: false,
                        })
                      }
                    >
                      <span className="text-sm font-medium">LiveKit WebRTC (experimental)</span>
                    </OptionCard>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    LiveKit requires a configured RTC server and worker. English and Hindi use
                    semantic turn detection; Telugu uses voice activity detection. RTC currently
                    supports three questions and uses deterministic questions without Gemini
                    refinement.
                  </p>
                </div>
                <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-background/40 p-4">
                  <input
                    type="checkbox"
                    className="mt-1 size-4 accent-primary"
                    checked={setup.compareNoiseEnhancement === true}
                    disabled={setup.voiceTransport === "livekit"}
                    onChange={(event) =>
                      actions.updateSetup({ compareNoiseEnhancement: event.target.checked })
                    }
                  />
                  <span>
                    <span className="block text-sm font-medium">
                      Run an experimental noise-filter comparison
                    </span>
                    <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
                      Sends one extra filtered copy of each answer to Gnani Prisma after its live
                      transcript. This adds delay and provider usage. It only compares transcript
                      text; it cannot tell which version is more accurate. Off by default.
                    </span>
                  </span>
                </label>
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
                [
                  "Length",
                  `${setup.questionTarget || 3} questions (${(setup.questionTarget || 3) === 3 ? "~10 min" : (setup.questionTarget || 3) === 5 ? "~20 min" : "~35 min"})`,
                ],
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

const DETECTABLE_SKILLS = [
  "python",
  "fastapi",
  "flask",
  "django",
  "pytorch",
  "tensorflow",
  "docker",
  "kubernetes",
  "postgresql",
  "redis",
  "react",
  "typescript",
  "golang",
  "rust",
  "aws",
  "gcp",
  "sqlite",
  "rag",
  "langchain",
  "llm",
  "kafka",
  "rest",
  "grpc",
  "ci/cd",
  "git",
];

function PersonaliseStep() {
  const setup = useAppStore((s) => s.setup);
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string>("");

  const onFile = async (file?: File) => {
    if (!file) return;
    if (!/\.(txt|md|json|pdf|docx)$/i.test(file.name)) {
      toast.error("Please upload a PDF, DOCX, TXT, MD, or JSON file");
      return;
    }
    if (file.size > 5_000_000) {
      toast.error("Resume files must be under 5 MB");
      return;
    }
    try {
      let text: string;
      if (/\.(pdf|docx)$/i.test(file.name)) {
        const form = new FormData();
        form.append("file", file);
        const response = await fetch("/api/resume/extract", { method: "POST", body: form });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Could not read this resume");
        text = result.text;
      } else {
        text = await file.text();
      }
      text = text.slice(0, 50_000).trim();
      if (!text) throw new Error("This file contains no readable text");
      actions.updateSetup({ highlights: text });
      setFileName(file.name);
      toast.success(`Loaded ${file.name} (${text.length} chars)`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not read this resume");
    }
  };

  const detectedSkills = DETECTABLE_SKILLS.filter((skill) =>
    (setup.highlights || "").toLowerCase().includes(skill),
  );

  const cleanGithub = (setup.github || "").trim().replace(/^https?:\/\/github\.com\//i, "");

  const loadSample = () => {
    actions.updateSetup({
      targetRole: setup.targetRole || "Backend Engineer",
      github: "fastapi/fastapi",
      highlights:
        "Built a high-throughput async WebSocket streaming service in Python/FastAPI with SQLite persistence, Redis caching, and Docker deployments. Implemented adaptive rate-limiting and zero-downtime database migrations.",
    });
    toast.success("Loaded sample profile & resume highlights");
  };

  return (
    <StepBody
      title="Make it about you (optional)"
      hint="This helps follow-up questions focus on your real projects and background."
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
          <p className="text-[11px] text-muted-foreground">
            Shapes technical focus and difficulty of scenario questions.
          </p>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="gh" className="flex items-center gap-1.5">
              <Github className="size-3.5" /> GitHub repository or username
            </Label>
            {cleanGithub && (
              <span className="flex items-center gap-1 text-[11px] text-teal">
                <CheckCircle2 className="size-3" /> Entered
              </span>
            )}
          </div>
          <Input
            id="gh"
            value={setup.github}
            onChange={(e) => actions.updateSetup({ github: e.target.value })}
            placeholder="e.g. username or github.com/owner/repo"
          />
          <p className="text-[11px] text-muted-foreground">
            {cleanGithub
              ? `The backend will try to inspect public GitHub data for ${cleanGithub}. Questions use it only when available.`
              : "Optional: Links your public projects to generate authentic follow-up questions."}
          </p>
        </div>
      </div>

      <div className="mt-5 space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="hl" className="flex items-center gap-1.5">
            <FileText className="size-3.5" /> Project & resume highlights
          </Label>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={loadSample}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <Sparkles className="size-3 text-teal" /> Load sample
            </button>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
            >
              <Upload className="size-3.5" /> Upload resume
            </button>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,.json"
            className="hidden"
            onChange={(e) => void onFile(e.target.files?.[0])}
          />
        </div>

        {fileName && (
          <div className="flex items-center justify-between rounded-lg border border-teal/20 bg-teal-soft/50 px-3 py-1.5 text-xs text-teal">
            <span className="flex items-center gap-1.5 truncate">
              <FileText className="size-3.5 shrink-0" /> {fileName}
            </span>
            <button
              type="button"
              onClick={() => {
                setFileName("");
                actions.updateSetup({ highlights: "" });
              }}
              className="hover:underline"
            >
              Clear
            </button>
          </div>
        )}

        <Textarea
          id="hl"
          rows={4}
          value={setup.highlights}
          onChange={(e) => actions.updateSetup({ highlights: e.target.value })}
          placeholder="e.g. Built a FastAPI streaming service with SQLite persistence, PyTorch inference pipeline, and Docker containerization…"
        />

        <label className="flex items-start gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={setup.useGemini === true}
            onChange={(event) => actions.updateSetup({ useGemini: event.target.checked })}
          />
          <span>
            Use Gemini to refine project questions from my technical resume highlights and verified
            public GitHub details. This sends those extracted details to Google.
          </span>
        </label>

        {detectedSkills.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-[11px] font-medium text-muted-foreground">Detected skills:</span>
            {detectedSkills.map((sk) => (
              <Badge
                key={sk}
                variant="outline"
                className="border-teal/30 bg-teal-soft/30 text-[10px] text-teal uppercase"
              >
                {sk}
              </Badge>
            ))}
          </div>
        )}
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
