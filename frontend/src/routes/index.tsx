import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight,
  AudioLines,
  BarChart3,
  CheckCircle2,
  FileSearch,
  GitBranch,
  Languages,
  MessagesSquare,
  Mic,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Logo } from "@/components/im/Logo";
import { ScoreRing } from "@/components/im/ScoreRing";
import { Meter } from "@/components/im/bits";
import { DOMAINS } from "@/lib/im/data";
import introductionImage from "@/assets/interviewmirror-introduction.jpg";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "InterviewMirror — Practise technical interviews in English, Telugu & Hindi" },
      {
        name: "description",
        content:
          "Realistic voice-based technical interview practice with smart follow-ups and clear, evidence-based feedback in English, Telugu or Hindi.",
      },
      {
        property: "og:title",
        content: "InterviewMirror — Practise the interview. Build the confidence.",
      },
      {
        property: "og:description",
        content:
          "Multilingual technical interview practice with smart follow-ups and evidence-based feedback.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Landing,
});

const STEPS = [
  {
    icon: <Sparkles />,
    title: "Choose your interview",
    body: "Pick a supported track and your language for a three-question practice interview.",
  },
  {
    icon: <Mic />,
    title: "Have a natural conversation",
    body: "Answer out loud. Gnani streams microphone audio and supplies the transcript when speech segments are recognized.",
  },
  {
    icon: <BarChart3 />,
    title: "Review and improve",
    body: "See what you nailed, what you missed, and the three next steps that will help most.",
  },
];

const FEATURES = [
  {
    icon: <AudioLines />,
    title: "Hands-free practice",
    body: "Questions are read aloud and you can answer by voice, just like a real call.",
  },
  {
    icon: <Languages />,
    title: "Speak your language",
    body: "English, Telugu or Hindi — with natural code-mixing for technical terms.",
  },
  {
    icon: <MessagesSquare />,
    title: "Adaptive follow-ups",
    body: "The interviewer selects the next prompt based on your previous answer.",
  },
  {
    icon: <GitBranch />,
    title: "Personalised to you",
    body: "Add your target role, GitHub and resume highlights to shape the questions.",
  },
  {
    icon: <FileSearch />,
    title: "Feedback with evidence",
    body: "Every score links back to what you actually said — no vague praise.",
  },
  {
    icon: <BarChart3 />,
    title: "Track your progress",
    body: "Watch your scores and covered topics grow from one session to the next.",
  },
];

function Landing() {
  return (
    <div className="min-h-screen bg-gradient-hero">
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/75 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <Logo />
          <nav className="hidden items-center gap-8 text-sm text-muted-foreground md:flex">
            <a href="#how" className="transition-colors hover:text-foreground">
              How it works
            </a>
            <a href="#features" className="transition-colors hover:text-foreground">
              Features
            </a>
            <a href="#tracks" className="transition-colors hover:text-foreground">
              Tracks
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" className="hidden sm:inline-flex">
              <Link to="/app">Open workspace</Link>
            </Button>
            <Button asChild>
              <Link to="/app/new">Start practising</Link>
            </Button>
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 pb-20 pt-16 lg:grid-cols-[1.05fr_1fr] lg:pt-24">
          <div className="animate-fade-up">
            <Badge variant="teal" className="mb-6 gap-2 px-3 py-1 text-xs">
              <span className="size-1.5 rounded-full bg-teal" /> English • తెలుగు • हिन्दी
            </Badge>
            <h1 className="text-4xl font-semibold leading-[1.08] sm:text-5xl lg:text-6xl">
              Practise the interview.
              <br />
              <span className="text-gradient-brand">Build the confidence.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg text-muted-foreground">
              Realistic technical interviews by voice, in the language you think in — with smart
              follow-ups and feedback that shows exactly where to improve.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg" variant="hero">
                <Link to="/app/new">
                  Start a free practice <ArrowRight />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <a href="#how">See how it works</a>
              </Button>
            </div>
            <dl className="mt-12 grid max-w-md grid-cols-3 gap-6">
              {[
                ["5", "interview tracks"],
                ["3", "languages"],
                ["3–7", "questions per session"],
              ].map(([v, l]) => (
                <div key={l}>
                  <dt className="font-display text-2xl font-semibold">{v}</dt>
                  <dd className="mt-1 text-xs text-muted-foreground">{l}</dd>
                </div>
              ))}
            </dl>
          </div>
          <HeroPreview />
        </section>

        {/* How it works */}
        <section id="how" className="border-t border-border/60 py-24">
          <div className="mx-auto max-w-6xl px-5">
            <SectionHeading eyebrow="How it works" title="Three calm, focused steps" />
            <div className="mt-12 grid gap-5 md:grid-cols-3">
              {STEPS.map((s, i) => (
                <div key={s.title} className="surface relative p-7">
                  <span className="absolute right-6 top-5 font-display text-5xl font-semibold text-muted/80">
                    0{i + 1}
                  </span>
                  <div className="mb-5 grid size-11 place-items-center rounded-xl bg-primary-soft text-primary [&_svg]:size-5">
                    {s.icon}
                  </div>
                  <h3 className="text-lg font-semibold">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Feedback preview */}
        <section className="py-8">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 lg:grid-cols-2">
            <div>
              <p className="eyebrow mb-3">Clear feedback</p>
              <h2 className="text-3xl font-semibold sm:text-4xl">
                Know exactly what to work on next
              </h2>
              <p className="mt-4 text-muted-foreground">
                After each session you get a simple report: an overall practice score, four skill
                areas, what went well, what was missing, and a short learning plan.
              </p>
              <ul className="mt-6 space-y-3 text-sm">
                {[
                  "Scores tied to the exact words you used",
                  "Fix transcription mistakes and re-check instantly",
                  "Download a study guide for later",
                ].map((t) => (
                  <li key={t} className="flex items-center gap-3">
                    <CheckCircle2 className="size-4 text-teal" /> {t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="surface p-6 sm:p-8">
              <div className="flex flex-col items-center gap-8 sm:flex-row">
                <ScoreRing score={78} />
                <div className="w-full flex-1 space-y-4">
                  {[
                    ["Technical accuracy", 82],
                    ["Design trade-offs", 76],
                    ["Project understanding", 80],
                    ["Communication", 74],
                  ].map(([l, v]) => (
                    <div key={l as string}>
                      <div className="mb-1.5 flex justify-between text-xs">
                        <span className="text-muted-foreground">{l}</span>
                        <span className="font-semibold tabular-nums">{v}</span>
                      </div>
                      <Meter value={v as number} />
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-6 rounded-xl border border-border bg-elevated/60 p-4 text-sm">
                <p className="text-xs font-semibold text-teal">Next step</p>
                <p className="mt-1">
                  Explain how a bounded queue prevents memory growth during audio streaming.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="py-24">
          <div className="mx-auto max-w-6xl px-5">
            <SectionHeading
              eyebrow="Features"
              title="Built for technical depth and clear speaking"
            />
            <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((f) => (
                <div
                  key={f.title}
                  className="surface group p-6 transition-colors hover:border-primary/40"
                >
                  <div className="mb-4 grid size-10 place-items-center rounded-xl bg-teal-soft text-teal [&_svg]:size-5">
                    {f.icon}
                  </div>
                  <h3 className="font-semibold">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Tracks */}
        <section id="tracks" className="border-y border-border/60 bg-card/40 py-24">
          <div className="mx-auto max-w-6xl px-5">
            <SectionHeading eyebrow="Interview tracks" title="Pick the role you're preparing for" />
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {DOMAINS.map((d) => (
                <div key={d.id} className="rounded-2xl border border-border bg-background/60 p-5">
                  <h3 className="text-sm font-semibold">{d.name}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{d.badge}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="py-24">
          <div className="mx-auto max-w-4xl px-5">
            <div className="surface relative overflow-hidden px-8 py-14 text-center">
              <div className="pointer-events-none absolute inset-0 bg-gradient-hero" />
              <div className="relative">
                <h2 className="text-3xl font-semibold sm:text-4xl">
                  Ready for your next interview?
                </h2>
                <p className="mx-auto mt-4 max-w-lg text-muted-foreground">
                  A quick 3-question session takes about ten minutes. No sign-up needed.
                </p>
                <div className="mt-8 flex flex-wrap justify-center gap-3">
                  <Button asChild size="lg" variant="hero">
                    <Link to="/app/new">
                      Start practising <ArrowRight />
                    </Link>
                  </Button>
                  <Button asChild size="lg" variant="outline">
                    <Link to="/app">Explore the workspace</Link>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/60 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-5 text-sm text-muted-foreground sm:flex-row">
          <Logo />
          <p>Practice guidance only — not a hiring assessment.</p>
        </div>
      </footer>
    </div>
  );
}

function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="max-w-2xl">
      <p className="eyebrow mb-3">{eyebrow}</p>
      <h2 className="text-3xl font-semibold sm:text-4xl">{title}</h2>
    </div>
  );
}

function HeroPreview() {
  return (
    <figure
      aria-label="Introducing InterviewMirror"
      className="min-w-0 animate-fade-up [animation-delay:120ms]"
    >
      <img
        src={introductionImage}
        alt="A candidate rehearsing an interview on a laptop, with a confident reflection in a mirror."
        width={1200}
        height={912}
        fetchPriority="high"
        className="aspect-[25/19] w-full rounded-lg object-cover"
      />
      <figcaption className="mt-5 border-t border-border pt-5">
        <p className="text-xs font-semibold uppercase text-teal">Meet InterviewMirror</p>
        <h2 className="mt-2 text-xl font-semibold tracking-normal">
          A rehearsal for your next big moment.
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Your space to practise, reflect and grow — in English, తెలుగు or हिन्दी.
        </p>
      </figcaption>
    </figure>
  );
}
