import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { ChevronRight, History, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EmptyState, PageHeader, ScoreBadge, StatusBadge } from "@/components/im/bits";
import { DOMAINS, LANGUAGES } from "@/lib/im/data";
import { actions, useAppStore } from "@/lib/im/store";
import type { Session } from "@/lib/im/types";

export const Route = createFileRoute("/app/history")({
  head: () => ({
    meta: [
      { title: "My interviews — InterviewMirror" },
      {
        name: "description",
        content: "Browse, filter and open every practice interview you've completed.",
      },
      { property: "og:title", content: "My interviews — InterviewMirror" },
      { property: "og:description", content: "All your practice interviews in one place." },
    ],
  }),
  component: HistoryPage,
});

function HistoryPage() {
  const sessions = useAppStore((s) => s.sessions);
  const [search, setSearch] = useState("");
  const [domain, setDomain] = useState("all");
  const [lang, setLang] = useState("all");
  const [status, setStatus] = useState("all");
  const [toDelete, setToDelete] = useState<Session | null>(null);

  const filtered = useMemo(
    () =>
      sessions.filter((s) => {
        if (domain !== "all" && s.domainId !== domain) return false;
        if (lang !== "all" && s.languageCode !== lang) return false;
        if (status !== "all" && s.status !== status) return false;
        if (
          search &&
          !`${s.targetRole} ${s.domainName}`.toLowerCase().includes(search.toLowerCase())
        )
          return false;
        return true;
      }),
    [sessions, search, domain, lang, status],
  );

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="My interviews"
        title="Interview history"
        description={`${sessions.length} interview${sessions.length === 1 ? "" : "s"} saved on this device.`}
        actions={
          <>
            <Button asChild>
              <Link to="/app/new">
                <Plus /> New interview
              </Link>
            </Button>
          </>
        }
      />

      {sessions.length === 0 ? (
        <EmptyState
          icon={<History />}
          title="No interviews yet"
          description="Your completed practice interviews will be listed here."
        >
          <Button asChild variant="hero">
            <Link to="/app/new">Start an interview</Link>
          </Button>
        </EmptyState>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-[1fr_auto_auto_auto]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by role or track"
                className="pl-9"
              />
            </div>
            <FilterSelect
              value={domain}
              onChange={setDomain}
              all="All tracks"
              options={DOMAINS.map((d): [string, string] => [d.id, d.name])}
            />
            <FilterSelect
              value={lang}
              onChange={setLang}
              all="All languages"
              options={LANGUAGES.map((l): [string, string] => [l.code, l.label])}
            />
            <FilterSelect
              value={status}
              onChange={setStatus}
              all="Any status"
              options={
                [
                  ["Completed", "Completed"],
                  ["Partial", "Partial"],
                ] as [string, string][]
              }
            />
          </div>

          {filtered.length === 0 ? (
            <div className="surface p-10 text-center text-sm text-muted-foreground">
              No interviews match these filters.
            </div>
          ) : (
            <ul className="surface divide-y divide-border overflow-hidden p-0">
              {filtered.map((s) => (
                <li
                  key={s.id}
                  className="group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-elevated/60"
                >
                  <Link
                    to="/app/report/$id"
                    params={{ id: s.id }}
                    className="flex min-w-0 flex-1 items-center gap-4"
                  >
                    <div className="hidden size-11 shrink-0 place-items-center rounded-xl bg-primary-soft font-display text-sm font-semibold text-primary sm:grid">
                      {s.domainName.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">{s.domainName}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {s.targetRole} • {LANGUAGES.find((l) => l.code === s.languageCode)?.label}
                      </p>
                    </div>
                    <div className="hidden text-right text-xs text-muted-foreground md:block">
                      <p>{s.date}</p>
                      <p>
                        {s.questionsCompleted} questions • {s.durationFormatted}
                      </p>
                    </div>
                    <StatusBadge status={s.status} />
                    <ScoreBadge score={s.overallScore} />
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </Link>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Delete interview"
                    onClick={() => setToDelete(s)}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this interview?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the report link for {toDelete?.domainName} from this browser. Backend
              data is managed separately.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (toDelete) actions.deleteSession(toDelete.id);
                toast("Interview deleted");
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function FilterSelect({
  value,
  onChange,
  all,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  all: string;
  options: [string, string][];
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-10 w-full md:w-44">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{all}</SelectItem>
        {options.map(([v, l]) => (
          <SelectItem key={v} value={v}>
            {l}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
