import { Link } from "@tanstack/react-router";
import { cn } from "@/lib/utils";

export function Logo({ className, to = "/" }: { className?: string; to?: string }) {
  return (
    <Link to={to} className={cn("group inline-flex items-center gap-2.5", className)}>
      <span className="relative grid size-9 place-items-center rounded-xl bg-gradient-brand shadow-glow">
        <span className="size-3.5 rounded-full border-2 border-primary-foreground/80" />
        <span className="absolute size-1.5 translate-x-[7px] -translate-y-[7px] rounded-full bg-primary-foreground/80" />
      </span>
      <span className="font-display text-[17px] font-semibold tracking-tight">
        Interview<span className="text-gradient-brand">Mirror</span>
      </span>
    </Link>
  );
}
