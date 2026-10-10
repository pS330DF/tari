/**
 * Typed IPC contract between the Electron main process and renderers.
 * Every channel's request/response types live here; main validates inputs.
 */
import type { AppSettings, SettingsPatch } from "./settings";

export type EngineState = "stopped" | "starting" | "ready" | "restarting" | "unavailable";

export interface EngineStatus {
  state: EngineState;
  port: number | null;
  token: string | null;
  version: string | null;
  restarts: number;
  lastError: string | null;
  python: string | null;
}

export interface CaptureSourceInfo {
  id: string;
  name: string;
  kind: "screen" | "window";
  thumbnail: string | null;
  appIcon: string | null;
  isTrainingLab: boolean;
  looksLikeValorant: boolean;
}

export interface SystemMetrics {
  ts: number;
  processes: { type: string; cpuPercent: number; memoryMB: number }[];
  totalCpuPercent: number;
  totalMemoryMB: number;
  gpu: { status: string; detail: string };
}

export interface AppInfo {
  version: string;
  electron: string;
  chrome: string;
  platform: string;
  dataDir: string;
  dev: boolean;
}

export interface CompanionSnapshot {
  status: "idle" | "watching" | "paused" | "engine_down";
  statusText: string;
  category: string | null;
  lastFeedback: string | null;
  lastFeedbackTone: "corrective" | "reinforcing" | "informational" | null;
  speaking: boolean;
  fps: number | null;
  latencyMs: number | null;
}

export interface Notice {
  level: "info" | "warning" | "error";
  message: string;
}

/** End-to-end validation mode (TARI_E2E_VIDEO): feeds a recorded video through the normal capture path. */
export interface E2EConfig {
  videoUrl: string;
  seconds: number;
}

export interface IpcContract {
  "settings:get": { req: void; res: AppSettings };
  "settings:set": { req: SettingsPatch; res: AppSettings };
  "capture:list-sources": { req: { thumbnails: boolean }; res: CaptureSourceInfo[] };
  "capture:select": { req: { id: string }; res: { ok: boolean; reason?: string } };
  "engine:status": { req: void; res: EngineStatus };
  "engine:restart": { req: void; res: EngineStatus };
  "lab:open": { req: void; res: { ok: boolean; reason?: string } };
  "companion:set-visible": { req: { visible: boolean }; res: { visible: boolean } };
  "system:metrics": { req: void; res: SystemMetrics };
  "app:info": { req: void; res: AppInfo };
  "e2e:config": { req: void; res: E2EConfig | null };
  "e2e:report": { req: Record<string, unknown>; res: { ok: boolean } };
  "e2e:screenshot": { req: { name: string; window?: "main" | "companion" }; res: { ok: boolean } };
}

export type IpcChannel = keyof IpcContract;

export interface IpcEvents {
  "engine:status-changed": EngineStatus;
  "settings:changed": AppSettings;
  notice: Notice;
  "companion:update": CompanionSnapshot;
  "companion:visibility": { visible: boolean };
}

/** Fire-and-forget messages from renderers to main. */
export interface IpcSends {
  "companion:publish": CompanionSnapshot;
}

export const TRAINING_LAB_TITLE = "TARI Training Lab";
