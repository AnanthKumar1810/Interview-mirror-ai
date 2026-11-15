import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { useState } from "react";
import { History, LayoutDashboard, LineChart, Menu, Mic, Settings, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Logo } from "@/components/im/Logo";
import { useAppStore } from "@/lib/im/store";

export const Route = createFileRoute("/app")({
  component: WorkspaceLayout,
});

const NAV = [
  { to: "/app", label: "Overview", icon: LayoutDashboard, exact: true },
  { to: "/app/new", label: "New interview", icon: Mic },
  { to: "/app/history", label: "My interviews", icon: History },
  { to: "/app/progress", label: "Progress", icon: LineChart },
  { to: "/app/settings", label: "Settings", icon: Settings },
] as const;

function NavList({ onNavigate }: { onNavigate?: (() => void) | undefined }) {
  return (
    <nav className="space-y-1">
      {NAV.map(({ to, label, icon: Icon, ...rest }) => (
        <Link
          key={to}
          to={to}
          onClick={onNavigate}
          activeOptions={{ exact: "exact" in rest }}
          className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-sidebar-foreground/75 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground data-[status=active]:bg-sidebar-accent data-[status=active]:text-sidebar-accent-foreground"
        >
          <Icon className="size-[18px]" />
          {label}
        </Link>
      ))}
    </nav>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: (() => void) | undefined }) {
  const profile = useAppStore((s) => s.profile);
  const live = useAppStore((s) => s.live);
  const initials = profile.name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="flex h-full flex-col gap-6 p-4">
      <div className="px-2 pt-2">
        <Logo />
      </div>
      {live && (
        <Link
          to="/interview"
          onClick={onNavigate}
          className="flex items-center gap-3 rounded-xl border border-teal/30 bg-teal-soft px-3 py-2.5 text-sm text-teal"
        >
          <span className="size-2 animate-pulse rounded-full bg-teal" />
          Resume interview
        </Link>
      )}
      <NavList onNavigate={onNavigate} />
      <div className="mt-auto space-y-3">
        <div className="rounded-2xl border border-sidebar-border bg-background/40 p-4">
          <Sparkles className="mb-2 size-4 text-teal" />
          <p className="text-sm font-semibold">Quick practice</p>
          <p className="mt-1 text-xs text-muted-foreground">3 questions • about 10 minutes</p>
          <Button asChild size="sm" className="mt-3 w-full">
            <Link to="/app/new" onClick={onNavigate}>
              Start now
            </Link>
          </Button>
        </div>
        <Link
          to="/app/settings"
          onClick={onNavigate}
          className="flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-sidebar-accent/60"
        >
          <span className="grid size-9 place-items-center rounded-full bg-gradient-brand text-xs font-bold text-primary-foreground">
            {initials || "C"}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">{profile.name}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {profile.targetRole}
            </span>
          </span>
        </Link>
      </div>
    </div>
  );
}

function WorkspaceLayout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-sidebar-border bg-sidebar lg:block">
        <SidebarBody />
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/85 px-4 backdrop-blur-xl lg:hidden">
        <Logo />
        <Button variant="ghost" size="icon" onClick={() => setOpen(true)} aria-label="Open menu">
          <Menu />
        </Button>
      </header>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72 border-sidebar-border bg-sidebar p-0">
          <SheetTitle className="sr-only">Menu</SheetTitle>
          <SidebarBody onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>

      <main className="lg:pl-64">
        <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
