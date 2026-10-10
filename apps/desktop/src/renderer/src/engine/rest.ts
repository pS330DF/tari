/** Engine REST client (loopback, token-authenticated). */
import type { PlayerProfile } from "@tari/shared-types";
import type { EngineStatus } from "../../../shared/ipc";

export interface SessionRow {
  session_id: string;
  player_id: string;
  started_ts: number;
  ended_ts: number | null;
  source_kind: string | null;
  source_label: string | null;
  environment: string | null;
  end_reason: string | null;
  frames_processed: number;
  frames_dropped: number;
  simulated: boolean;
  exposures: number;
  recs: number;
}

export interface SessionMetricRow {
  metric: string;
  value: number;
  unit: string;
  samples: number;
  method: string;
}

export interface SessionDetail extends SessionRow {
  metrics: SessionMetricRow[];
  recommendations: { rule_id: string; observation: string; suggestion: string; confidence: number; created_ts_ms: number; priority: string }[];
  event_counts: Record<string, number>;
}

async function get<T>(engine: EngineStatus, path: string): Promise<T> {
  if (engine.state !== "ready" || !engine.port || !engine.token) throw new Error("Engine is not running");
  const res = await fetch(`http://127.0.0.1:${engine.port}${path}`, { headers: { "x-tari-token": engine.token } });
  if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => res.statusText)}`);
  return (await res.json()) as T;
}

export const fetchSessions = (e: EngineStatus) => get<SessionRow[]>(e, "/v1/sessions?limit=100");
export const fetchSession = (e: EngineStatus, id: string) => get<SessionDetail>(e, `/v1/sessions/${encodeURIComponent(id)}`);
export const fetchProfile = (e: EngineStatus) => get<PlayerProfile>(e, "/v1/profile");
