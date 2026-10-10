import type { CoachingRecommendation } from "@tari/shared-types";
import { ChevronRight, Info } from "lucide-react";
import { useState } from "react";
import type { MeasuredValue } from "../engine/session-metrics";
import { cn, fmt } from "../lib/utils";
import { useApp } from "../store/app-store";
import { TariMark } from "./TariMark";
import { Tip } from "./ui/tooltip";

export function CompanionPanel() {
  const engine = useApp((s) => s.engine);
  const capture = useApp((s) => s.capture);
  const live = useApp((s) => s.live.state);
  const voice = useApp((s) => s.voice);
  const recs = useApp((s) => s.recommendations);
  const sessionId = useApp((s) => s.session.id);
  const nowSource = live?.ts_ms ?? 0;
  const active = recs.filter((r) => r.expiration.expires_ts_ms > nowSource);
  const current = active[0] ?? null;
  const earlier = recs.filter((r) => r !== current).slice(0, 6);

  let status = "Idle. Choose a source to begin.";
  if (engine.state !== "ready") status = engine.state === "unavailable" ? engine.lastError ?? "Engine unavailable." : "Starting the analysis engine…";
  else if (capture.state === "running" && !sessionId) status = "Connecting to the engine…";
  else if (capture.state === "running" && live?.coaching_mode === "live_training") status = "Watching your training session.";
  else if (capture.state === "running") status = "Paused: this source is not the verified Training Lab.";

  return (
    <aside className="flex w-[360px] shrink-0 flex-col border-l border-line bg-panel">
      <div className="flex items-center gap-3 border-b border-line px-4 py-3.5">
        <TariMark size={22} active={live?.coaching_mode === "live_training"} />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold tracking-[0.14em]">TARI</div>
          <div className="truncate text-[12px] text-fg-muted">{status}</div>
        </div>
        <VoiceIndicator speaking={voice.speaking} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <section className="px-4 pt-4 pb-3">
          <div className="eyebrow mb-2">Now</div>
          {current ? <RecommendationCard rec={current} /> : <Waiting />}
        </section>
        <Measurements />
        {earlier.length > 0 && (
          <section className="border-t border-line px-4 py-3">
            <div className="eyebrow mb-2">Earlier</div>
            <ul className="space-y-2">
              {earlier.map((r) => (
                <li key={r.rec_id} className="text-[12px] leading-snug text-fg-muted">
                  <span className="text-fg-subtle tabular">{fmtClock(r.created_ts_ms)}</span> {r.short_text}
                </li>
              ))}
            </ul>
          </section>
        )}
        <Timeline />
      </div>
    </aside>
  );
}

function fmtClock(ts: number): string {
  const d = new Date(ts);
  return `${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}

function VoiceIndicator({ speaking }: { speaking: boolean }) {
  return (
    <Tip content={speaking ? "TARI is speaking" : "Voice idle"}>
      <div className="flex h-5 items-center gap-[3px]" aria-label={speaking ? "speaking" : "voice idle"}>
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className={cn("h-4 w-[3px] rounded-full", speaking ? "voice-bar bg-accent" : "bg-line-strong")}
            style={speaking ? { animationDelay: `${i * 0.12}s` } : { transform: "scaleY(0.35)" }}
          />
        ))}
      </div>
    </Tip>
  );
}

function Waiting() {
  const capture = useApp((s) => s.capture);
  const m = useApp((s) => s.measurements);
  const text =
    capture.state !== "running"
      ? "Feedback appears here during a session."
      : `Measuring. Feedback appears once enough exposures are measured (${m?.placement.samples ?? 0}/4 held-angle exposures so far).`;
  return <p className="rounded-md border border-dashed border-line-strong px-3 py-3 text-[12.5px] leading-relaxed text-fg-muted">{text}</p>;
}

function RecommendationCard({ rec }: { rec: CoachingRecommendation }) {
  const [open, setOpen] = useState(false);
  const toneLabel = rec.tone === "reinforcing" ? "Holding well" : rec.tone === "corrective" ? "Correction" : "Note";
  const confLabel = rec.confidence >= 0.75 ? "high" : rec.confidence >= 0.55 ? "medium" : "low";
  return (
    <article key={rec.rec_id} className="fade-in rounded-md border border-line-strong bg-raised">
      <div className="px-3.5 pt-3 pb-3">
        <div className="mb-1.5 flex items-center gap-2 text-[11px]">
          <span className={cn("font-semibold uppercase tracking-wider", rec.tone === "reinforcing" ? "text-accent" : "text-warn")}>{toneLabel}</span>
          <span className="text-fg-subtle">·</span>
          <span className="text-fg-subtle uppercase tracking-wider">{rec.domain}</span>
          <span className="ml-auto text-fg-subtle">{rec.priority}</span>
        </div>
        <p className="text-[13.5px] leading-relaxed text-fg">{rec.observation}</p>
        <p className="mt-2 text-[13px] leading-relaxed text-accent-strong">{rec.suggestion}</p>
      </div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 border-t border-line px-3.5 py-2 text-left text-[11.5px] text-fg-muted hover:text-fg"
      >
        <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
        Evidence · confidence {rec.confidence.toFixed(2)} ({confLabel})
      </button>
      {open && (
        <div className="space-y-2.5 border-t border-line px-3.5 py-3 text-[12px] leading-relaxed">
          {rec.evidence.map((e) => (
            <div key={e.metric}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-[11.5px] text-fg">{e.metric}</span>
                <span className="tabular text-fg">{e.value} {e.unit} · n={e.samples}</span>
              </div>
              <p className="mt-0.5 text-fg-muted">{e.method}</p>
              {e.detail && <p className="text-fg-subtle">{e.detail}</p>}
            </div>
          ))}
          <p className="text-fg-muted"><span className="text-fg-subtle">Why it matters · </span>{rec.reasoning}</p>
          <p className="text-fg-subtle">
            Confidence is a heuristic certainty score from detection quality and sample count, not a probability.
          </p>
        </div>
      )}
    </article>
  );
}

function Measurements() {
  const m = useApp((s) => s.measurements);
  const rows: { v: MeasuredValue | undefined; render: (v: MeasuredValue) => string }[] = [
    { v: m?.placement, render: (v) => (v.value === null ? "—" : `${Math.abs(v.value).toFixed(1)}° ${v.value > 0 ? "low" : v.value < 0 ? "high" : ""}`) },
    { v: m?.anglePrep, render: (v) => fmt(v.value, 1, "°") },
    { v: m?.acquisition, render: (v) => (v.value === null ? "—" : `${Math.round(v.value)} ms`) },
    { v: m?.overshoot, render: (v) => (v.samples ? `${v.value} of ${v.samples}` : "—") },
    { v: m?.undershoot, render: (v) => (v.samples ? `${v.value} of ${v.samples}` : "—") },
    { v: m?.unstableShots, render: (v) => (v.samples ? `${v.value} of ${v.samples}` : "—") },
    { v: m?.movingShots, render: (v) => (v.samples ? `${v.value} of ${v.samples}` : "—") },
    { v: m?.onHeadShots, render: (v) => (v.samples ? `${v.value} of ${v.samples}` : "—") },
  ];
  return (
    <section className="border-t border-line px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="eyebrow">Measured this session</span>
        <span className="text-[11px] text-fg-subtle tabular">{m?.exposures ?? 0} exposures</span>
      </div>
      <dl className="space-y-1">
        {rows.map(({ v, render }, i) =>
          v ? (
            <div key={v.label} className="flex items-center justify-between gap-3 py-0.5">
              <dt className="flex items-center gap-1.5 text-[12.5px] text-fg-muted">
                {v.label}
                <Tip content={<span>{v.method}{v.samples ? ` (n=${v.samples})` : ""}</span>}>
                  <Info className="size-3 text-fg-subtle" />
                </Tip>
              </dt>
              <dd className={cn("tabular text-[12.5px]", v.samples ? "text-fg" : "text-fg-subtle")}>{render(v)}</dd>
            </div>
          ) : (
            <div key={i} className="flex justify-between py-0.5 text-[12.5px] text-fg-subtle">
              <span>{["Head-level placement", "Angle preparation", "Acquisition time", "Overshoots", "Undershoots", "Shots during view motion", "Shots while moving", "Crosshair on head at shot"][i]}</span>
              <span>—</span>
            </div>
          ),
        )}
      </dl>
    </section>
  );
}

function Timeline() {
  const items = useApp((s) => s.timeline);
  if (!items.length) return null;
  return (
    <section className="border-t border-line px-4 py-3">
      <div className="eyebrow mb-2">Timeline</div>
      <ol className="space-y-1.5">
        {items.slice(0, 40).map((t) => (
          <li key={t.id} className="flex items-start gap-2 text-[12px] leading-snug">
            <span className={cn("mt-[5px] size-1.5 shrink-0 rounded-full", { good: "bg-accent", warn: "bg-warn", info: "bg-cyan", neutral: "bg-fg-subtle" }[t.tone])} />
            <span className="w-16 shrink-0 text-fg-subtle">{t.kind}</span>
            <span className="text-fg-muted">{t.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

