/** Mode A: compact, draggable, always-on-top companion. */
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { CompanionSnapshot } from "../../shared/ipc";
import { TariMark } from "./components/TariMark";
import { cn } from "./lib/utils";
import "./styles.css";

function Companion() {
  const [snap, setSnap] = useState<CompanionSnapshot | null>(null);
  useEffect(() => window.tari.on("companion:update", setSnap), []);
  const status = snap?.status ?? "idle";
  const dot = { watching: "bg-accent", paused: "bg-warn", engine_down: "bg-danger", idle: "bg-fg-subtle" }[status];
  return (
    <div className="drag h-full w-full p-1.5">
      <div className="flex h-full flex-col rounded-lg border border-line-strong bg-[#0b0e11]/95 px-3.5 py-2.5 shadow-2xl shadow-black/60">
        <div className="flex items-center gap-2">
          <TariMark size={15} active={status === "watching"} />
          <span className="text-[11.5px] font-semibold tracking-[0.16em]">TARI</span>
          <span className={cn("size-1.5 rounded-full", dot)} />
          <span className="truncate text-[11.5px] text-fg-muted">{snap?.statusText ?? "Waiting for TARI…"}</span>
          <div className="ml-auto flex h-3.5 items-center gap-[2px]">
            {[0, 1, 2].map((i) => (
              <span key={i} className={cn("h-3.5 w-[2px] rounded-full", snap?.speaking ? "voice-bar bg-accent" : "bg-line-strong")}
                style={snap?.speaking ? { animationDelay: `${i * 0.12}s` } : { transform: "scaleY(0.35)" }} />
            ))}
          </div>
        </div>
        <p className={cn("mt-2 line-clamp-2 text-[13px] leading-snug", snap?.lastFeedbackTone === "reinforcing" ? "text-accent-strong" : "text-fg")}>
          {snap?.lastFeedback ?? (status === "watching" ? "Watching. Measuring your exposures…" : "No feedback yet.")}
        </p>
        <div className="mt-auto flex items-center gap-3 text-[10.5px] text-fg-subtle">
          {snap?.category && <span className="uppercase tracking-wider">{snap.category}</span>}
          <span className="tabular ml-auto">{snap?.fps != null ? `${snap.fps.toFixed(0)} fps` : "— fps"}</span>
          <span className="tabular">{snap?.latencyMs != null ? `${Math.round(snap.latencyMs)} ms` : "— ms"}</span>
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Companion />
  </StrictMode>,
);
