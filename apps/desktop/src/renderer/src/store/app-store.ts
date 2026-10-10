/** Reactive application state (Zustand). Per-frame data bypasses React via the frame bus. */
import { create } from "zustand";
import type {
  CoachingRecommendation,
  EngineCapabilities,
  GameState,
  ModuleStatus,
  PerformanceSnapshot,
  SessionSummary,
} from "@tari/shared-types";
import type { LatencySummary } from "@tari/telemetry";
import type { AppSettings } from "../../../shared/settings";
import type { CaptureSourceInfo, EngineStatus, Notice, SystemMetrics } from "../../../shared/ipc";
import type { ClientStats, WsStatus } from "../capture/protocol";
import type { LiveMeasurements } from "../engine/session-metrics";

export type View = "live" | "sessions" | "profile" | "settings";

export interface TimelineItem {
  id: string;
  ts: number;
  kind: string;
  text: string;
  tone: "neutral" | "good" | "warn" | "info";
}

export interface ActiveSource {
  kind: "desktop" | "file";
  label: string;
  desktop?: CaptureSourceInfo;
}

export interface AppStore {
  view: View;
  settings: AppSettings | null;
  engine: EngineStatus;
  ws: WsStatus;
  capabilities: EngineCapabilities | null;
  capture: { state: "idle" | "starting" | "running" | "error"; source: ActiveSource | null; error: string | null };
  session: { id: string | null; startedTs: number | null; lastSummary: SessionSummary | null; persistence: string | null };
  live: { state: GameState | null; modules: ModuleStatus[] };
  recommendations: CoachingRecommendation[];
  timeline: TimelineItem[];
  measurements: LiveMeasurements | null;
  telemetry: {
    engine: PerformanceSnapshot | null;
    client: ClientStats | null;
    system: SystemMetrics | null;
    visualLatency: LatencySummary | null;
    voiceLatency: LatencySummary | null;
  };
  notices: (Notice & { id: string; ts: number })[];
  voice: { speaking: boolean; text: string | null };
  companionVisible: boolean;
  set: (patch: Partial<AppStore>) => void;
  pushNotice: (n: Notice) => void;
  dismissNotice: (id: string) => void;
  addRecommendations: (recs: CoachingRecommendation[]) => void;
  pushTimeline: (items: TimelineItem[]) => void;
}

const initialEngine: EngineStatus = { state: "stopped", port: null, token: null, version: null, restarts: 0, lastError: null, python: null };

export const useApp = create<AppStore>((set) => ({
  view: "live",
  settings: null,
  engine: initialEngine,
  ws: "disconnected",
  capabilities: null,
  capture: { state: "idle", source: null, error: null },
  session: { id: null, startedTs: null, lastSummary: null, persistence: null },
  live: { state: null, modules: [] },
  recommendations: [],
  timeline: [],
  measurements: null,
  telemetry: { engine: null, client: null, system: null, visualLatency: null, voiceLatency: null },
  notices: [],
  voice: { speaking: false, text: null },
  companionVisible: false,
  set: (patch) => set(patch),
  pushNotice: (n) =>
    set((s) => {
      if (s.notices.some((x) => x.message === n.message)) return s;
      return { notices: [...s.notices.slice(-4), { ...n, id: crypto.randomUUID(), ts: Date.now() }] };
    }),
  dismissNotice: (id) => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })),
  addRecommendations: (recs) =>
    set((s) => ({ recommendations: [...recs.slice().reverse(), ...s.recommendations].slice(0, 24) })),
  pushTimeline: (items) => set((s) => ({ timeline: [...items.slice().reverse(), ...s.timeline].slice(0, 80) })),
}));
