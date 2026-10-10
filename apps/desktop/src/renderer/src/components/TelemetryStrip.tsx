import type { LatencySummary } from "@tari/telemetry";
import { ChevronUp } from "lucide-react";
import { useState } from "react";
import { cn } from "../lib/utils";
import { useApp } from "../store/app-store";
import { Tip } from "./ui/tooltip";

function ms(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v < 10 ? v.toFixed(1) : Math.round(v)} ms`;
}

function Stat({ label, value, tip, warn }: { label: string; value: string; tip: string; warn?: boolean }) {
  return (
    <Tip content={tip}>
      <div className="flex items-baseline gap-1.5 whitespace-nowrap">
        <span className="text-[11px] text-fg-subtle">{label}</span>
        <span className={cn("tabular text-[12px]", warn ? "text-warn" : "text-fg")}>{value}</span>
      </div>
    </Tip>
  );
}

export function TelemetryStrip() {
  const [open, setOpen] = useState(false);
  const t = useApp((s) => s.telemetry);
  const c = t.client;
  const e = t.engine;
  const dropped = (e?.counters["dropped_stale"] ?? 0) + (e?.counters["dropped_superseded"] ?? 0) + (e?.counters["dropped_out_of_order"] ?? 0);
  const e2e = c?.endToEndMs;
  return (
    <div className="shrink-0 border-t border-line">
      <div className="flex h-9 items-center gap-5 px-4">
        <Stat label="Capture" value={c ? `${c.captureFps.toFixed(0)} fps` : "—"} tip="Frames delivered by the capture source per second." />
        <Stat label="Analyzed" value={c ? `${c.resultFps.toFixed(0)} fps` : "—"} tip="Frames analyzed by the engine per second (frames beyond the target rate or while busy are skipped, not queued)." />
        <Stat label="Frame → result" value={e2e ? `${ms(e2e.p50)} · p95 ${ms(e2e.p95)}` : "—"} warn={(e2e?.p95 ?? 0) > 150} tip="Time from frame acquisition to its analysis result arriving in the app (p50 · p95, last 10 s)." />
        <Stat label="Frame → screen" value={t.visualLatency?.count ? `${ms(t.visualLatency.p50)} · p95 ${ms(t.visualLatency.p95)}` : "—"} warn={(t.visualLatency?.p95 ?? 0) > 150} tip="Time from frame acquisition until its feedback was drawn in the viewer (target < 150 ms)." />
        <Stat label="Dropped" value={e ? String(dropped) : "—"} tip="Frames the engine discarded because a newer frame arrived or they were too old to be useful." />
        <Stat label="CPU" value={t.system ? `${Math.round(t.system.totalCpuPercent)}% app · ${e?.gauges["engine_cpu_percent"] ?? "—"}% engine` : "—"} tip="CPU use of TARI processes (100% = one core)." />
        <Stat label="GPU" value="n/a" tip={t.system?.gpu.detail ?? e?.unavailable["gpu_utilization_percent"] ?? "GPU utilization is not measured on this system."} />
        <button onClick={() => setOpen((v) => !v)} className="ml-auto flex items-center gap-1 text-[11.5px] text-fg-muted hover:text-fg">
          Details <ChevronUp className={cn("size-3.5 transition-transform", !open && "rotate-180")} />
        </button>
      </div>
      {open && <Details />}
    </div>
  );
}

function Row({ name, s, note }: { name: string; s: LatencySummary | undefined | null; note: string }) {
  return (
    <tr className="border-t border-line">
      <td className="py-1.5 pr-4 text-fg-muted">{name}</td>
      <td className="tabular pr-4 text-right">{ms(s?.p50)}</td>
      <td className="tabular pr-4 text-right">{ms(s?.p95)}</td>
      <td className="tabular pr-4 text-right">{ms(s?.p99)}</td>
      <td className="tabular pr-4 text-right text-fg-subtle">{s?.count ?? 0}</td>
      <td className="text-fg-subtle">{note}</td>
    </tr>
  );
}

function Details() {
  const t = useApp((s) => s.telemetry);
  const e = t.engine;
  const c = t.client;
  return (
    <div className="max-h-64 overflow-y-auto border-t border-line px-4 py-3 text-[12px]">
      <table className="w-full">
        <thead>
          <tr className="text-left text-[11px] text-fg-subtle">
            <th className="pb-1 font-medium">Stage</th>
            <th className="pb-1 pr-4 text-right font-medium">p50</th>
            <th className="pb-1 pr-4 text-right font-medium">p95</th>
            <th className="pb-1 pr-4 text-right font-medium">p99</th>
            <th className="pb-1 pr-4 text-right font-medium">n</th>
            <th className="pb-1 font-medium">What it measures</th>
          </tr>
        </thead>
        <tbody>
          <Row name="Frame prepare" s={c?.prepareMs} note="Scale + crop + encode in the capture worker" />
          <Row name="Perception" s={e?.latencies["perception_ms"]} note="All vision modules for one frame" />
          <Row name="State update" s={e?.latencies["state_ms"]} note="Tracking, temporal measurements, events (target < 15 ms)" />
          <Row name="Coaching" s={e?.latencies["coaching_ms"]} note="Rules, filtering, overlay + voice generation (target < 25 ms)" />
          <Row name="Engine total" s={e?.latencies["engine_total_ms"]} note="Receive to result ready" />
          <Row name="Round trip" s={c?.rttMs} note="Frame sent to result received" />
          <Row name="Frame → result" s={c?.endToEndMs} note="Acquisition to result received" />
          <Row name="Frame → screen" s={t.visualLatency} note="Acquisition to feedback drawn" />
          <Row name="Voice start" s={t.voiceLatency} note="Observed frame to speech start" />
        </tbody>
      </table>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-fg-muted">
        <span>Engine memory <span className="tabular text-fg">{e?.gauges["engine_rss_mb"] ?? "—"} MB</span></span>
        <span>App memory <span className="tabular text-fg">{t.system?.totalMemoryMB ?? "—"} MB</span></span>
        <span>In flight <span className="tabular text-fg">{c?.inFlight ?? "—"}</span></span>
        <span>Source <span className="tabular text-fg">{c?.sourceWidth ? `${c.sourceWidth}×${c.sourceHeight}` : "—"}</span></span>
        <span>Skipped at source <span className="tabular text-fg">{c ? (c.counts["skip_rate"] ?? 0) + (c.counts["skip_backpressure"] ?? 0) : "—"}</span></span>
      </div>
    </div>
  );
}
