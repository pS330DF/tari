import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

const tones = {
  neutral: "bg-raised text-fg-muted border-line-strong",
  accent: "bg-accent/10 text-accent-strong border-accent/25",
  warn: "bg-warn/10 text-warn border-warn/25",
  danger: "bg-danger/10 text-danger border-danger/25",
  info: "bg-cyan/10 text-cyan border-cyan/25",
} as const;

export function Badge({ tone = "neutral", className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-px text-[11px] font-medium leading-4", tones[tone], className)}
      {...props}
    />
  );
}

export function StatusDot({ tone }: { tone: "ok" | "warn" | "danger" | "idle" | "busy" }) {
  const color = { ok: "bg-accent", warn: "bg-warn", danger: "bg-danger", idle: "bg-fg-subtle", busy: "bg-cyan" }[tone];
  return (
    <span className="relative inline-flex size-2">
      {tone === "busy" && <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-50", color)} />}
      <span className={cn("relative inline-flex size-2 rounded-full", color)} />
    </span>
  );
}
