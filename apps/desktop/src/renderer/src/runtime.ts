/**
 * Renderer runtime: wires capture, the engine stream, voice, and UI state.
 *
 * Session lifecycle: Start -> capture source -> (engine socket open) ->
 * start_session -> frames flow -> results/overlays/voice -> Stop -> end_session.
 * If the engine restarts, the socket reconnects and a new session starts while
 * capture keeps running; nothing is fabricated while the engine is down.
 */
import type { ClientMetricsMessage, FrameResultMessage, PerformanceSnapshot, StartSessionMessage } from "@tari/shared-types";
import { SCHEMA_VERSION } from "@tari/shared-types";
import { RollingWindow, epochMs, summarize } from "@tari/telemetry";
import type { CaptureSourceInfo, CompanionSnapshot, EngineStatus } from "../../shared/ipc";
import type { AppSettings } from "../../shared/settings";
import { CaptureController } from "./capture/capture-controller";
import type { PumpConfig, WorkerOut } from "./capture/protocol";
import { fetchSession } from "./engine/rest";
import { SessionMetrics } from "./engine/session-metrics";
import { useApp, type TimelineItem } from "./store/app-store";
import { BrowserSpeechEngine, VoiceController } from "./voice/voice-controller";

export interface FrameBus {
  version: number;
  bitmap: ImageBitmap | null;
  result: FrameResultMessage | null;
  receivedTs: number;
  drawnVersion: number;
}

const DOMAIN_LABEL: Record<string, string> = {
  aim: "Aim", utility: "Utility", positioning: "Positioning", tactical: "Tactics", agent: "Agent", team: "Team",
  communication: "Comms", system: "System",
};

class TariRuntime {
  readonly capture = new CaptureController();
  readonly voice: VoiceController;
  readonly frameBus: FrameBus = { version: 0, bitmap: null, result: null, receivedTs: 0, drawnVersion: 0 };
  readonly visualLatency = new RollingWindow(10_000);
  readonly metrics = new SessionMetrics();
  private wsUrl: string | null = null;
  private sessionRequested = false;
  private lastStateUpdate = 0;
  private lastCompanion = 0;
  private started = false;
  /** Whole-run samples, only collected during E2E validation runs. */
  private e2e: { active: boolean; endToEnd: number[]; visual: number[]; results: number; drawn: number; events: Record<string, number>; recs: string[]; voice: number } = {
    active: false, endToEnd: [], visual: [], results: 0, drawn: 0, events: {}, recs: [], voice: 0,
  };

  constructor() {
    this.voice = new VoiceController(
      new BrowserSpeechEngine(),
      { enabled: true, voiceURI: null, rate: 1.05, volume: 0.9, cooldownMs: 8000, maxQueue: 4 },
      epochMs,
    );
    this.voice.onSpeakingChange = (speaking, text) => {
      useApp.getState().set({ voice: { speaking, text } });
      this.publishCompanion(true);
    };
  }

  async init(): Promise<void> {
    if (this.started) return;
    this.started = true;
    this.capture.subscribe((m) => this.onWorker(m));
    window.tari.on("engine:status-changed", (s) => this.onEngineStatus(s));
    window.tari.on("settings:changed", (s) => this.applySettings(s));
    window.tari.on("notice", (n) => useApp.getState().pushNotice(n));
    window.tari.on("companion:visibility", ({ visible }) => useApp.getState().set({ companionVisible: visible }));
    const [settings, engine] = await Promise.all([window.tari.invoke("settings:get", undefined), window.tari.invoke("engine:status", undefined)]);
    this.applySettings(settings);
    this.onEngineStatus(engine);
    setInterval(() => void this.pollSystem(), 2000);
    setInterval(() => this.pushClientMetrics(), 5000);
    const e2e = await window.tari.invoke("e2e:config", undefined);
    if (e2e) void this.runE2E(e2e.videoUrl, e2e.seconds);
  }

  /**
   * End-to-end validation: waits for the engine, feeds a recorded video through the
   * normal video-file capture path, then reports what actually happened.
   */
  private async runE2E(url: string, seconds: number): Promise<void> {
    const wait = async (cond: () => boolean, ms: number) => {
      const t0 = Date.now();
      while (!cond() && Date.now() - t0 < ms) await new Promise((r) => setTimeout(r, 100));
      return cond();
    };
    const report: Record<string, unknown> = { started: new Date().toISOString(), video: url, seconds };
    try {
      this.e2e.active = true;
      this.voice.configure({ enabled: false }); // count voice instructions, but do not speak during automated runs
      const ready = await wait(() => useApp.getState().engine.state === "ready" && useApp.getState().ws === "open", 60_000);
      report.engineReady = ready;
      if (!ready) throw new Error(`engine not ready: ${JSON.stringify(useApp.getState().engine)}`);
      const blob = await (await fetch(url)).blob();
      await this.startFile(new File([blob], "lab-recording.webm", { type: blob.type || "video/webm" }));
      report.sessionStarted = await wait(() => useApp.getState().session.id !== null, 15_000);
      const sessionId = useApp.getState().session.id;
      await window.tari.invoke("companion:set-visible", { visible: true });
      await new Promise((r) => setTimeout(r, (seconds * 1000) / 2));
      await window.tari.invoke("e2e:screenshot", { name: "live" });
      await window.tari.invoke("e2e:screenshot", { name: "companion", window: "companion" });
      await new Promise((r) => setTimeout(r, (seconds * 1000) / 2));
      const client = useApp.getState().telemetry.client;
      const engineSnap = useApp.getState().telemetry.engine;
      this.stop();
      report.sessionEnded = await wait(() => useApp.getState().session.lastSummary?.session_id === sessionId, 10_000);
      await new Promise((r) => setTimeout(r, 500));
      report.sessionId = sessionId;
      report.summary = useApp.getState().session.lastSummary;
      report.client = client;
      report.engineTelemetry = engineSnap;
      report.endToEndMs = summarize(this.e2e.endToEnd);
      report.visualFeedbackMs = summarize(this.e2e.visual);
      report.results = this.e2e.results;
      report.framesPresented = this.e2e.drawn;
      report.events = this.e2e.events;
      report.recommendations = this.e2e.recs;
      report.voiceInstructions = this.e2e.voice;
      report.capabilities = useApp.getState().capabilities;
      if (sessionId) report.persisted = await fetchSession(useApp.getState().engine, sessionId).catch((e) => ({ error: String(e) }));
      for (const view of ["sessions", "profile", "settings"] as const) {
        useApp.getState().set({ view });
        await new Promise((r) => setTimeout(r, 1200));
        await window.tari.invoke("e2e:screenshot", { name: view });
      }
      useApp.getState().set({ view: "live" });
      report.ok = true;
    } catch (err) {
      report.ok = false;
      report.error = String((err as Error)?.stack ?? err);
    }
    report.finished = new Date().toISOString();
    await window.tari.invoke("e2e:report", report);
  }

  private applySettings(s: AppSettings): void {
    useApp.getState().set({ settings: s });
    this.voice.configure({ enabled: s.voice.enabled && s.coaching.voice_frequency !== "off", voiceURI: s.voice.voiceURI, rate: s.voice.rate, volume: s.voice.volume });
    this.capture.configure(this.pumpConfig(s));
    if (useApp.getState().session.id) {
      this.capture.control({ schema_version: SCHEMA_VERSION, type: "update_settings", coaching: s.coaching, perception: s.perception });
    }
  }

  private pumpConfig(s: AppSettings): PumpConfig {
    return {
      targetFps: s.capture.targetFps,
      maxInFlight: s.capture.maxInFlight,
      analysisHeight: s.capture.analysisHeight,
      centerSize: s.capture.centerSize,
      keepBitmaps: true,
      displayMaxWidth: 1600,
    };
  }

  private onEngineStatus(s: EngineStatus): void {
    useApp.getState().set({ engine: s });
    if (s.state === "ready" && s.port && s.token) {
      const url = `ws://127.0.0.1:${s.port}/v1/stream?token=${s.token}`;
      if (url !== this.wsUrl) {
        if (this.wsUrl) this.capture.disconnect();
        this.wsUrl = url;
        this.capture.connect(url);
      }
    } else if (this.wsUrl && s.state !== "ready") {
      this.wsUrl = null;
      this.capture.disconnect();
    }
    this.publishCompanion(true);
  }

  // -- session control -----------------------------------------------------------
  async startDesktop(source: CaptureSourceInfo): Promise<void> {
    await this.startWith({ kind: "desktop", label: source.name, desktop: source }, (cfg) => this.capture.startDesktop(source, cfg));
  }

  async startFile(file: File): Promise<void> {
    await this.startWith({ kind: "file", label: file.name }, (cfg) => this.capture.startFile(file, cfg));
  }

  private async startWith(source: { kind: "desktop" | "file"; label: string; desktop?: CaptureSourceInfo }, run: (cfg: PumpConfig) => Promise<void>): Promise<void> {
    const store = useApp.getState();
    if (!store.settings) return;
    store.set({ capture: { state: "starting", source, error: null }, recommendations: [], timeline: [], measurements: null });
    this.metrics.reset();
    try {
      await run(this.pumpConfig(store.settings));
      useApp.getState().set({ capture: { state: "running", source, error: null } });
      this.sessionRequested = true;
      this.requestSession();
    } catch (err) {
      useApp.getState().set({ capture: { state: "error", source, error: friendlyCaptureError(err) } });
    }
  }

  private requestSession(): void {
    const store = useApp.getState();
    const src = this.capture.current;
    if (!this.sessionRequested || !src || store.ws !== "open" || !store.settings || store.session.id) return;
    const msg: StartSessionMessage = {
      schema_version: SCHEMA_VERSION,
      type: "start_session",
      session_id: null,
      player_id: "local",
      source: { source_id: src.sourceId, source_kind: src.sourceKind, label: src.label },
      coaching: store.settings.coaching,
      perception: store.settings.perception,
    };
    this.capture.control(msg);
  }

  stop(): void {
    this.sessionRequested = false;
    if (useApp.getState().session.id) {
      this.pushClientMetrics();
      this.capture.control({ schema_version: SCHEMA_VERSION, type: "end_session", reason: "user_stopped" });
    }
    this.capture.stop();
    this.voice.stopAll();
    useApp.getState().set({ capture: { state: "idle", source: null, error: null } });
    this.clearFrame();
  }

  private clearFrame(): void {
    this.frameBus.bitmap?.close();
    this.frameBus.bitmap = null;
    this.frameBus.result = null;
    this.frameBus.version++;
  }

  // -- worker messages ---------------------------------------------------------------
  private onWorker(m: WorkerOut): void {
    const store = useApp.getState();
    switch (m.type) {
      case "status":
        store.set({ ws: m.ws });
        if (m.ws === "open") this.requestSession();
        else store.set({ session: { ...store.session, id: null } });
        this.publishCompanion(true);
        break;
      case "engine":
        this.onEngineMessage(m.message);
        break;
      case "result":
        this.onResult(m.message, m.bitmap, m.receivedTs);
        break;
      case "stats":
        store.set({ telemetry: { ...store.telemetry, client: m.stats, visualLatency: this.visualLatency.summary(epochMs()), voiceLatency: this.voice.latency.summary(epochMs()) } });
        break;
      case "capture-ended":
        if (store.capture.state === "running") {
          this.stop();
          store.pushNotice({ level: "info", message: "Capture source closed. Session ended." });
        }
        break;
      case "error":
        if (!/control message not sent/.test(m.message)) console.warn("[tari]", m.message);
        break;
      case "dropped":
        break;
    }
  }

  private onEngineMessage(msg: Extract<WorkerOut, { type: "engine" }>["message"]): void {
    const store = useApp.getState();
    switch (msg.type) {
      case "hello":
        store.set({ capabilities: msg.capabilities });
        break;
      case "session_started":
        store.set({ session: { id: msg.session_id, startedTs: msg.started_ts_ms, lastSummary: store.session.lastSummary, persistence: msg.persistence } });
        this.metrics.reset();
        break;
      case "session_ended":
        store.set({ session: { id: null, startedTs: null, lastSummary: msg.summary, persistence: store.session.persistence } });
        if (this.sessionRequested) this.requestSession();
        break;
      case "telemetry":
        store.set({ telemetry: { ...store.telemetry, engine: msg.snapshot } });
        break;
      case "notice":
        store.pushNotice({ level: msg.level, message: msg.message });
        if (msg.priority === "P0") {
          this.voice.enqueue({
            schema_version: SCHEMA_VERSION, voice_id: crypto.randomUUID(), session_id: store.session.id ?? "", created_ts_ms: epochMs(),
            priority: "P0", domain: "system", text: msg.message.split(". ")[0] ?? msg.message, language: store.settings?.coaching.language ?? "en",
            dedupe_key: `notice.${msg.code}`, interrupt: false, ttl_ms: 6000, rec_id: null,
          });
        }
        break;
      default:
        break;
    }
  }

  private onResult(result: FrameResultMessage, bitmap: ImageBitmap | null, receivedTs: number): void {
    const bus = this.frameBus;
    if (bus.result && result.perception.session_id === bus.result.perception.session_id
        && result.perception.frame_id < bus.result.perception.frame_id) {
      bitmap?.close(); // an older result arriving late never replaces a newer one on screen
      return;
    }
    bus.bitmap?.close(); // the viewer draws synchronously, so the previous frame is no longer needed
    bus.bitmap = bitmap;
    bus.result = result;
    bus.receivedTs = receivedTs;
    bus.version++;

    const store = useApp.getState();
    if (this.e2e.active) {
      this.e2e.results++;
      this.e2e.endToEnd.push(receivedTs - result.perception.acquired_ts_ms);
      for (const e of result.events) this.e2e.events[e.type] = (this.e2e.events[e.type] ?? 0) + 1;
      this.e2e.recs.push(...result.recommendations.map((r) => r.rule_id));
      this.e2e.voice += result.voice.length;
    }
    if (result.recommendations.length) store.addRecommendations(result.recommendations);
    for (const v of result.voice) this.voice.enqueue(v);
    if (this.metrics.ingest(result.events)) store.set({ measurements: this.metrics.summary() });
    const items = timelineItems(result);
    if (items.length) store.pushTimeline(items);
    const now = performance.now();
    if (now - this.lastStateUpdate > 160) {
      this.lastStateUpdate = now;
      store.set({ live: { state: result.state, modules: result.perception.modules } });
    }
    this.publishCompanion(false);
  }

  /** Called by the viewer when it presents a result: records visual feedback latency. */
  notePresented(result: FrameResultMessage): void {
    const now = epochMs();
    this.visualLatency.push(now - result.perception.acquired_ts_ms, now);
    if (this.e2e.active) {
      this.e2e.drawn++;
      this.e2e.visual.push(now - result.perception.acquired_ts_ms);
    }
  }

  // -- telemetry -----------------------------------------------------------------------
  private async pollSystem(): Promise<void> {
    try {
      const system = await window.tari.invoke("system:metrics", undefined);
      const s = useApp.getState();
      s.set({ telemetry: { ...s.telemetry, system } });
    } catch {
      /* main process busy; next poll will retry */
    }
  }

  private pushClientMetrics(): void {
    const s = useApp.getState();
    const c = s.telemetry.client;
    if (!s.session.id || !c) return;
    const now = epochMs();
    const snapshot: PerformanceSnapshot = {
      schema_version: SCHEMA_VERSION,
      ts_ms: now,
      window_s: 10,
      source: "desktop",
      latencies: {
        round_trip_ms: c.rttMs,
        end_to_end_ms: c.endToEndMs,
        frame_prepare_ms: c.prepareMs,
        visual_feedback_ms: this.visualLatency.summary(now),
        voice_start_ms: this.voice.latency.summary(now),
      },
      rates: { capture_fps: c.captureFps, sent_fps: c.sentFps, result_fps: c.resultFps },
      counters: Object.fromEntries(Object.entries(c.counts).map(([k, v]) => [k, Math.round(v)])),
      gauges: {
        in_flight: c.inFlight,
        desktop_cpu_percent: s.telemetry.system?.totalCpuPercent ?? null,
        desktop_memory_mb: s.telemetry.system?.totalMemoryMB ?? null,
      },
      unavailable: { gpu_utilization_percent: s.telemetry.system?.gpu.detail ?? "not reported" },
    };
    const msg: ClientMetricsMessage = { schema_version: SCHEMA_VERSION, type: "client_metrics", snapshot };
    this.capture.control(msg);
  }

  // -- companion ------------------------------------------------------------------------
  publishCompanion(force: boolean): void {
    const now = performance.now();
    if (!force && now - this.lastCompanion < 250) return;
    this.lastCompanion = now;
    const s = useApp.getState();
    const st = this.frameBus.result?.state;
    const latest = s.recommendations[0];
    let status: CompanionSnapshot["status"] = "idle";
    let statusText = "Idle";
    if (s.engine.state !== "ready") {
      status = "engine_down";
      statusText = s.engine.state === "unavailable" ? "Engine unavailable" : "Engine starting…";
    } else if (s.capture.state === "running") {
      if (st?.coaching_mode === "live_training") {
        status = "watching";
        statusText = st.drill.value === "flick" ? "Training Lab · Flick" : st.drill.value === "angle_hold" ? "Training Lab · Angle hold" : "Training Lab";
      } else {
        status = "paused";
        statusText = "Paused · source not verified";
      }
    }
    const fps = s.telemetry.client?.resultFps ?? null;
    const lat = s.telemetry.client?.endToEndMs.p50 ?? null;
    const snap: CompanionSnapshot = {
      status,
      statusText,
      category: latest ? DOMAIN_LABEL[latest.domain] ?? latest.domain : status === "watching" ? "Aim" : null,
      lastFeedback: latest?.short_text ?? null,
      lastFeedbackTone: latest?.tone ?? null,
      speaking: s.voice.speaking,
      fps,
      latencyMs: lat,
    };
    window.tari.send("companion:publish", snap);
  }
}

function timelineItems(r: FrameResultMessage): TimelineItem[] {
  const out: TimelineItem[] = [];
  for (const e of r.events) {
    switch (e.type) {
      case "target_exposed": {
        const y = e.entry_error_deg.y;
        out.push({ id: e.event_id, ts: e.ts_ms, kind: "Exposure", tone: Math.abs(y) <= 0.6 ? "good" : "warn",
          text: `Entered ${Math.abs(y).toFixed(1)}° ${y > 0 ? "below" : "above"} head · ${Math.abs(e.entry_error_deg.x).toFixed(1)}° wide` });
        break;
      }
      case "target_acquired":
        out.push({ id: e.event_id, ts: e.ts_ms, kind: "Acquired", tone: "neutral", text: `${Math.round(e.acquisition_ms)} ms ±${Math.round(e.resolution_ms)}` });
        break;
      case "flick_analyzed":
        out.push({ id: e.event_id, ts: e.ts_ms, kind: "Flick", tone: e.outcome === "clean" ? "good" : e.outcome === "unresolved" ? "neutral" : "warn",
          text: e.outcome === "overshoot" ? `Overshot by ${(e.overshoot_deg ?? 0).toFixed(1)}°` : e.outcome === "undershoot" ? `Stopped ${(e.residual_deg ?? 0).toFixed(1)}° short` : e.outcome === "clean" ? "Clean" : "Unresolved" });
        break;
      case "shot_fired":
        out.push({ id: e.event_id, ts: e.ts_ms, kind: "Shot", tone: e.on_head ? "good" : "neutral",
          text: [e.on_head === null ? null : e.on_head ? "on head" : "off head", e.movement_error ? "moving" : null,
            e.view_speed_dps != null && e.view_speed_dps > 40 ? `view ${Math.round(e.view_speed_dps)}°/s` : null].filter(Boolean).join(" · ") || "fired" });
        break;
      case "environment_changed":
        out.push({ id: e.event_id, ts: e.ts_ms, kind: "Source", tone: "info", text: e.current === "training_lab" ? "Training Lab verified" : "Source not verified" });
        break;
      case "perception_notice":
        out.push({ id: e.event_id, ts: e.ts_ms, kind: "Notice", tone: "warn", text: e.message });
        break;
      case "source_reconfigured":
        if (e.reason !== "session_start") out.push({ id: e.event_id, ts: e.ts_ms, kind: "Source", tone: "info", text: e.reason === "capture_gap" ? `Capture gap ${Math.round(e.gap_ms ?? 0)} ms` : `Resolution ${e.width}×${e.height}` });
        break;
    }
  }
  return out;
}

function friendlyCaptureError(err: unknown): string {
  const text = String((err as Error)?.message ?? err);
  if (/Permission|NotAllowed/i.test(text)) {
    return window.tari.platform === "darwin"
      ? "Screen capture was not permitted. Allow TARI (or Electron in development) under System Settings → Privacy & Security → Screen Recording, then restart."
      : "Screen capture was not permitted by the system.";
  }
  return text;
}

export const runtime = new TariRuntime();
