import { cn } from "@/lib/utils";

export type OrbState = "idle" | "speaking" | "listening" | "answering" | "thinking";

export const ORB_LABELS: Record<OrbState, { title: string; hint: string }> = {
  idle: { title: "Ready", hint: "Start whenever you are." },
  speaking: {
    title: "Interviewer speaking",
    hint: "Listen to the question — you can interrupt any time.",
  },
  listening: { title: "Your turn", hint: "Take a breath, then speak your answer." },
  answering: { title: "Capturing your answer", hint: "Keep going — pauses are fine." },
  thinking: { title: "Reviewing your answer", hint: "Matching what you said to the key ideas…" },
};

export function VoiceOrb({
  state,
  size = 180,
  className,
}: {
  state: OrbState;
  size?: number;
  className?: string;
}) {
  return (
    <div
      className={cn("orb", className)}
      data-state={state}
      style={{ ["--orb-size" as string]: `${size}px` }}
      role="img"
      aria-label={ORB_LABELS[state].title}
    >
      <span className="orb__ring" />
      <span className="orb__ring" />
      <span className="orb__ring" />
      <span className="orb__core" />
    </div>
  );
}
