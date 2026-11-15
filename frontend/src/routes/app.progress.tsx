import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { ArrowRight, LineChart as LineIcon, Target } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Meter, PageHeader, Panel, PanelTitle } from "@/components/im/bits";
import { recurringGaps, topicStats } from "@/lib/im/insights";
import { actions, useAppStore } from "@/lib/im/store";

export const Route = createFileRoute("/app/progress")({
  head: () => ({
    meta: [
      { title: "Progress — InterviewMirror" },
      {
        name: "description",
        content: "See your practice score trend, skill balance, topic coverage and recurring gaps.",
      },
      { property: "og:title", content: "Progress — InterviewMirror" },
      {
        property: "og:description",
        content: "Track how your interview answers improve over time.",
      },
    ],
  }),
  component: ProgressPage,
});

const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 12,
  color: "var(--foreground)",
  fontSize: 12,
};

function ProgressPage() {
  const sessions = useAppStore((s) => s.sessions);
  const navigate = useNavigate();
  const topics = useMemo(() => topicStats(sessions), [sessions]);
  const gaps = useMemo(() => recurringGaps(sessions), [sessions]);
  const trend = useMemo(
    () =>
      [...sessions]
        .reverse()
        .map((s, i) => ({ name: `#${i + 1}`, date: s.date.slice(5, 10), score: s.overallScore })),
    [sessions],
  );

  const latest = sessions[0];
  if (!latest) {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow="Progress" title="Skills & progress" />
        <EmptyState
          icon={<LineIcon />}
          title="Not enough data yet"
          description="Complete an interview to see your score trend and skill balance."
        >
          <Button asChild variant="hero">
            <Link to="/app/new">Start an interview</Link>
          </Button>
        </EmptyState>
      </div>
    );
  }

  const radar = [
    { k: "Accuracy", v: latest.dimensions.technicalAccuracy },
    { k: "Trade-offs", v: latest.dimensions.designTradeoffs },
    { k: "Projects", v: latest.dimensions.projectUnderstanding },
    { k: "Communication", v: latest.dimensions.communicationClarity },
    {
      k: "Coverage",
      v: Math.round((latest.questionsCompleted / Math.max(1, latest.questionTarget)) * 100),
    },
  ];

  const practiseTopic = (domainId: string) => {
    actions.updateSetup({ domainId, questionTarget: 3 });
    navigate({ to: "/app/new" });
  };

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Progress"
        title="Skills & progress"
        description="How your practice scores and topic coverage are developing over time."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Panel className="lg:col-span-3">
          <PanelTitle title="Score trend" description="Overall practice score for each session." />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                <defs>
                  <linearGradient id="trend-line" x1="0" x2="1" y1="0" y2="0">
                    <stop offset="0%" stopColor="var(--primary)" />
                    <stop offset="100%" stopColor="var(--teal)" />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="var(--muted-foreground)"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  domain={[40, 100]}
                  stroke="var(--muted-foreground)"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: "var(--border)" }} />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="url(#trend-line)"
                  strokeWidth={3}
                  dot={{ r: 5, fill: "var(--teal)", strokeWidth: 0 }}
                  activeDot={{ r: 7 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel className="lg:col-span-2">
          <PanelTitle title="Skill balance" description="From your latest session." />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radar} outerRadius="72%">
                <PolarGrid stroke="var(--border)" />
                <PolarAngleAxis
                  dataKey="k"
                  tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                />
                <Radar
                  dataKey="v"
                  stroke="var(--primary)"
                  fill="var(--primary)"
                  fillOpacity={0.25}
                  strokeWidth={2}
                />
                <Tooltip contentStyle={tooltipStyle} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Panel className="lg:col-span-3">
          <PanelTitle title="Topics practised" description="Select a topic to practise it again." />
          <ul className="space-y-1">
            {topics.map((t) => (
              <li key={t.topic}>
                <button
                  onClick={() => practiseTopic(t.domainId)}
                  className="group flex w-full items-center gap-4 rounded-xl p-3 text-left transition-colors hover:bg-elevated"
                >
                  <div className="min-w-0 flex-1">
                    <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                      <span className="truncate font-medium">{t.topic}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {t.count} attempt{t.count > 1 ? "s" : ""} • best {t.best}
                      </span>
                    </div>
                    <Meter
                      value={t.best}
                      tone={t.best >= 80 ? "teal" : t.best >= 70 ? "primary" : "warning"}
                    />
                  </div>
                  <ArrowRight className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel className="lg:col-span-2">
          <PanelTitle title="Recurring gaps" description="Ideas you've missed most often." />
          {gaps.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recurring gaps — great work.</p>
          ) : (
            <ul className="space-y-3">
              {gaps.map((g) => (
                <li
                  key={g.concept}
                  className="rounded-xl border border-border bg-background/40 p-4"
                >
                  <div className="flex items-start gap-3">
                    <Target className="mt-0.5 size-4 shrink-0 text-warning" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{g.concept}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{g.topic}</p>
                      <Badge variant="warning" className="mt-2">
                        Missed {g.count}×
                      </Badge>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
