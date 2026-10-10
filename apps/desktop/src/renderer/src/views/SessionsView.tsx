import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { fetchSession, fetchSessions, type SessionDetail, type SessionRow } from "../engine/rest";
import { ago, cn } from "../lib/utils";
import { useApp } from "../store/app-store";

const METRIC_LABEL: Record<string, string> = {
  vertical_entry_offset_deg: "Vertical entry offset (median, + = low)",
  vertical_entry_abs_offset_deg: "Head-level placement (median |offset|)",
  horizontal_entry_abs_offset_deg: "Angle preparation (median |offset|)",
  acquisition_time_ms: "Acquisition time (median)",
  overshoot_flicks: "Overshoot flicks",
  undershoot_flicks: "Undershoot flicks",
  unstable_shots: "Shots during view motion",
  moving_shots: "Shots while moving",
};

function duration(r: SessionRow): string {
  if (!r.ended_ts) return "in progress";
  const s = Math.round((r.ended_ts - r.started_ts) / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function SessionsView() {
  const engine = useApp((s) => s.engine);
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await fetchSessions(engine));
      setError(null);
    } catch (err) {
      setError(String((err as Error).message ?? err));
    }
  }, [engine]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selected) return;
    fetchSession(engine, selected).then(setDetail).catch((err) => setError(String(err)));
  }, [selected, engine]);

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 items-center gap-3 border-b border-line px-5">
          <h1 className="text-[14px] font-semibold">Sessions</h1>
          <span className="text-[12px] text-fg-muted">Stored locally on this device</span>
          <Button className="ml-auto" variant="ghost" size="sm" onClick={() => void load()}>
            <RefreshCw /> Refresh
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {error && <p className="px-5 py-4 text-[12.5px] text-danger">{error}</p>}
          {!error && rows.length === 0 && <p className="px-5 py-6 text-[12.5px] text-fg-muted">No sessions yet. Start one from the Live tab.</p>}
          <table className="w-full text-[12.5px]">
            <thead className="sticky top-0 bg-bg text-left text-[11px] text-fg-subtle">
              <tr>
                <th className="px-5 py-2 font-medium">Started</th>
                <th className="py-2 font-medium">Source</th>
                <th className="py-2 font-medium">Environment</th>
                <th className="py-2 text-right font-medium">Duration</th>
                <th className="py-2 text-right font-medium">Exposures</th>
                <th className="py-2 text-right font-medium">Feedback</th>
                <th className="px-5 py-2 text-right font-medium">Frames</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.session_id}
                  onClick={() => setSelected(r.session_id)}
                  className={cn("cursor-default border-t border-line hover:bg-raised/60", selected === r.session_id && "bg-raised")}
                >
                  <td className="px-5 py-2 text-fg">{new Date(r.started_ts).toLocaleString()} <span className="text-fg-subtle">· {ago(r.started_ts)}</span></td>
                  <td className="max-w-56 truncate py-2 text-fg-muted">{r.source_label || r.source_kind}{r.simulated && <Badge className="ml-2">simulated</Badge>}</td>
                  <td className="py-2">{r.environment === "training_lab" ? <Badge tone="accent">Training Lab</Badge> : <Badge>{r.environment ?? "—"}</Badge>}</td>
                  <td className="tabular py-2 text-right text-fg-muted">{duration(r)}</td>
                  <td className="tabular py-2 text-right">{r.exposures}</td>
                  <td className="tabular py-2 text-right">{r.recs}</td>
                  <td className="tabular px-5 py-2 text-right text-fg-muted">{r.frames_processed}{r.frames_dropped ? ` (+${r.frames_dropped} dropped)` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <aside className="w-[400px] shrink-0 overflow-y-auto border-l border-line bg-panel px-5 py-4">
        {!detail ? (
          <p className="text-[12.5px] text-fg-muted">Select a session to see its measurements.</p>
        ) : (
          <div className="space-y-5">
            <div>
              <div className="eyebrow mb-1">Session</div>
              <p className="font-mono text-[12px] text-fg-muted">{detail.session_id}</p>
              <p className="mt-1 text-[12.5px] text-fg-muted">Ended: {detail.end_reason ?? "—"}</p>
            </div>
            <div>
              <div className="eyebrow mb-2">Measurements</div>
              {detail.metrics.length === 0 && <p className="text-[12.5px] text-fg-muted">No measurements were recorded.</p>}
              <dl className="space-y-2.5">
                {detail.metrics.map((m) => (
                  <div key={m.metric}>
                    <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
                      <dt className="text-fg-muted">{METRIC_LABEL[m.metric] ?? m.metric}</dt>
                      <dd className="tabular text-fg">
                        {m.unit === "deg" ? `${m.value.toFixed(2)}°` : m.unit === "ms" ? `${Math.round(m.value)} ms` : `${m.value} of ${m.samples}`}
                      </dd>
                    </div>
                    <p className="text-[11.5px] text-fg-subtle">n = {m.samples}</p>
                  </div>
                ))}
              </dl>
            </div>
            <div>
              <div className="eyebrow mb-2">Feedback given</div>
              {detail.recommendations.length === 0 && <p className="text-[12.5px] text-fg-muted">None.</p>}
              <ul className="space-y-3">
                {detail.recommendations.map((r, i) => (
                  <li key={i} className="text-[12.5px] leading-relaxed">
                    <p className="text-fg">{r.observation}</p>
                    <p className="text-accent-strong">{r.suggestion}</p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
