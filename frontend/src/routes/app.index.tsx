import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { ArrowRight, CheckCircle2, ClipboardList, Mic, Target, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  EmptyState,
  Meter,
  PageHeader,
  Panel,
  PanelTitle,
  ScoreBadge,
  StatTile,
  StatusBadge,
} from "@/components/im/bits";
import { actions, useAppStore } from "@/lib/im/store";
import { DOMAINS, LANGUAGES } from "@/lib/im/data";
import { topicStats } from "@/lib/im/insights";

export const Route = createFileRoute("/app/")({
  head: () => ({
    meta: [
      { title: "Overview — InterviewMirror" },
      {
        name: "description",
        content:
          "Your interview practice at a glance: recent sessions, scores and what to practise next.",
      },
      { property: "og:title", content: "Overview — InterviewMirror" },
      { property: "og:description", content: "Your interview practice at a glance." },
    ],
  }),
  component: Overview,
});

function Overview() {
  const sessions = useAppStore((s) => s.sessions);
  const profile = useAppStore((s) => s.profile);
  const topics = useMemo(() => topicStats(sessions), [sessions]);
  const latest = sessions[0];
  const firstName = profile.name.split(" ")[0];

  if (!latest) {
    return (
      <div className="space-y-8">
        <PageHeader
          eyebrow="Overview"
          title={`Welcome, ${firstName}`}
          description="Your workspace is empty — let's run your first practice interview."
        />
        <EmptyState
          icon={<Mic />}
          title="No interviews yet"
          description="A quick 3-question session takes about ten minutes and unlocks your first report and learning plan."
        >
          <Button asChild variant="hero">
            <Link to="/app/new">Set up first interview</Link>
          </Button>
        </EmptyState>
      </div>
    );
  }

  const strong = topics.filter((t) => t.best >= 80).length;
  const gaps = latest.improvements.length;
  const domain = DOMAINS.find((d) => d.id === latest.domainId);
  const nextFocus = latest.turns.find((t) => t.missingConcepts.length > 0);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Overview"
        title={`Welcome back, ${firstName}`}
        description="Pick up where you left off, or start a fresh practice session."
        actions={
          <Button asChild variant="hero">
            <Link to="/app/new">
              <Mic /> New interview
            </Link>
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Sessions completed"
          value={sessions.length}
          hint="Saved on this device"
          icon={<ClipboardList />}
        />
        <StatTile
          label="Latest score"
          value={
            <>
              {latest.overallScore}
              <span className="text-base text-muted-foreground"> /100</span>
            </>
          }
          hint={latest.domainName}
          icon={<TrendingUp />}
        />
        <StatTile
          label="Strong topics"
          value={strong}
          hint={`of ${topics.length} practised`}
          icon={<CheckCircle2 />}
        />
        <StatTile
          label="Focus areas"
          value={gaps}
          hint="From your latest session"
          icon={<Target />}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Panel className="relative overflow-hidden lg:col-span-3">
          <div className="pointer-events-none absolute inset-0 bg-gradient-hero opacity-70" />
          <div className="relative">
            <Badge variant="teal" className="mb-4">
              Suggested next practice
            </Badge>
            <h2 className="text-xl font-semibold">
              {nextFocus ? `Strengthen: ${nextFocus.topic}` : `Go deeper in ${latest.domainName}`}
            </h2>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              {nextFocus?.recommendation ??
                "You covered the key ideas well. Try a longer session at a harder level."}
            </p>
            <div className="mt-5 flex flex-wrap gap-2 text-xs">
              <Badge variant="muted">{domain?.name}</Badge>
              <Badge variant="muted">
                {LANGUAGES.find((l) => l.code === latest.languageCode)?.label}
              </Badge>
              <Badge variant="muted">3 questions</Badge>
            </div>
            <Button asChild className="mt-6">
              <Link
                to="/app/new"
                onClick={() =>
                  actions.updateSetup({
                    domainId: latest.domainId,
                    languageCode: latest.languageCode,
                    questionTarget: 3,
                  })
                }
              >
                Start this session <ArrowRight />
              </Link>
            </Button>
          </div>
        </Panel>

        <Panel className="lg:col-span-2">
          <PanelTitle
            title="Recent interviews"
            action={
              <Link
                to="/app/history"
                className="text-xs font-semibold text-primary hover:underline"
              >
                View all
              </Link>
            }
          />
          <ul className="space-y-2">
            {sessions.slice(0, 4).map((s) => (
              <li key={s.id}>
                <Link
                  to="/app/report/$id"
                  params={{ id: s.id }}
                  className="flex items-center gap-3 rounded-xl p-3 transition-colors hover:bg-elevated"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{s.domainName}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {s.date} • {s.questionsCompleted} questions
                    </p>
                  </div>
                  <StatusBadge status={s.status} />
                  <ScoreBadge score={s.overallScore} />
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel>
        <PanelTitle
          title="Skills snapshot"
          description="Your best score on each topic you've practised."
          action={
            <Link to="/app/progress" className="text-xs font-semibold text-primary hover:underline">
              Full progress
            </Link>
          }
        />
        <div className="grid gap-x-10 gap-y-5 md:grid-cols-2">
          {topics.slice(0, 6).map((t) => (
            <div key={t.topic}>
              <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                <span className="truncate font-medium">{t.topic}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {t.best >= 80 ? "Strong" : t.best >= 70 ? "Developing" : "Needs practice"} •{" "}
                  {t.best}
                </span>
              </div>
              <Meter
                value={t.best}
                tone={t.best >= 80 ? "teal" : t.best >= 70 ? "primary" : "warning"}
              />
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
