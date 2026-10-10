import type { PlayerProfile } from "@tari/shared-types";
import { useEffect, useState } from "react";
import { Badge } from "../components/ui/badge";
import { fetchProfile } from "../engine/rest";
import { useApp } from "../store/app-store";

const TREND: Record<string, { label: string; tone: "accent" | "warn" | "neutral" }> = {
  improving: { label: "Improving", tone: "accent" },
  declining: { label: "Declining", tone: "warn" },
  stable: { label: "Stable", tone: "neutral" },
  insufficient_data: { label: "Not enough data", tone: "neutral" },
};

function value(v: number, unit: string): string {
  if (unit === "ms") return `${Math.round(v)}`;
  if (unit === "ratio") return v.toFixed(2);
  return v.toFixed(2);
}

export function ProfileView() {
  const engine = useApp((s) => s.engine);
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProfile(engine).then(setProfile).catch((e) => setError(String((e as Error).message ?? e)));
  }, [engine]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-6 py-6">
        <h1 className="text-[16px] font-semibold">Progress</h1>
        <p className="mt-1 max-w-2xl text-[12.5px] leading-relaxed text-fg-muted">
          Built only from measurements stored on this device. A session counts toward a skill when it has enough samples;
          trends need at least three such sessions. Simulated (test) sessions are excluded.
        </p>
        {error && <p className="mt-4 text-[12.5px] text-danger">{error}</p>}
        {profile && (
          <>
            <div className="mt-5 grid grid-cols-3 gap-px overflow-hidden rounded-md border border-line bg-line">
              {[
                ["Sessions", profile.sessions_total],
                ["Validated sessions", profile.validated_sessions],
                ["Exposures measured", profile.total_exposures],
              ].map(([k, v]) => (
                <div key={k} className="bg-panel px-4 py-3">
                  <div className="eyebrow">{k}</div>
                  <div className="tabular mt-1 text-[20px] font-medium">{v}</div>
                </div>
              ))}
            </div>
            {profile.next_focus && (
              <div className="mt-4 rounded-md border border-accent/25 bg-accent/5 px-4 py-3">
                <div className="eyebrow text-accent">Next focus</div>
                <p className="mt-1 text-[13px] text-fg">{profile.next_focus_reason}</p>
              </div>
            )}
            <div className="mt-6 space-y-px overflow-hidden rounded-md border border-line bg-line">
              {profile.skills.map((s) => (
                <div key={s.skill} className="bg-panel px-4 py-3.5">
                  <div className="flex items-center gap-3">
                    <span className="text-[13px] font-medium">{s.label}</span>
                    <Badge tone={TREND[s.trend]?.tone ?? "neutral"}>{TREND[s.trend]?.label ?? s.trend}</Badge>
                    <span className="ml-auto text-[11.5px] text-fg-subtle">{s.unit === "ratio" ? "share of samples" : s.unit} · lower is better</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                    {s.points.length === 0 && <span className="text-[12.5px] text-fg-subtle">No validated sessions yet.</span>}
                    {s.points.slice(-8).map((p) => (
                      <span key={p.session_id} className="tabular text-[12.5px] text-fg" title={`${new Date(p.ts_ms).toLocaleString()} · n=${p.samples}`}>
                        {value(p.value, s.unit)}
                      </span>
                    ))}
                  </div>
                  {s.trend_detail && <p className="mt-1.5 text-[12px] text-fg-muted">{s.trend_detail}</p>}
                </div>
              ))}
            </div>
            {profile.recurring_issues.length > 0 && (
              <div className="mt-6">
                <div className="eyebrow mb-2">Recurring feedback</div>
                <ul className="space-y-1 text-[12.5px] text-fg-muted">
                  {profile.recurring_issues.map((r) => (
                    <li key={r.rule_id}>
                      <span className="font-mono text-fg">{r.rule_id}</span> in {r.sessions} sessions ({r.occurrences} times)
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
