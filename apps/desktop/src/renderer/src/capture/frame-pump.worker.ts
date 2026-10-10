/// <reference lib="webworker" />
/**
 * Frame pump (dedicated worker).
 *
 * Reads VideoFrames from the capture track, applies the bounded scheduler,
 * builds the analysis regions, encodes FramePackets, and owns the engine
 * WebSocket. Each result is paired with the bitmap of the exact frame it was
 * computed from, so the viewer can draw frame + overlay as one unit.
 */
import { encodeFramePacket, parseEngineMessage } from "@tari/shared-types";
import { RateMeter, RollingWindow, epochMs } from "@tari/telemetry";
import type { ClientStats, PumpConfig, SourceDescriptor, WorkerIn, WorkerOut } from "./protocol";
import { analysisSize, centerRect, displaySize } from "./regions";
import { FrameScheduler } from "./scheduler";

const post = (msg: WorkerOut, transfer: Transferable[] = []) => (self as unknown as Worker).postMessage(msg, transfer);

let config: PumpConfig = { targetFps: 30, maxInFlight: 1, analysisHeight: 540, centerSize: 384, keepBitmaps: true, displayMaxWidth: 1600 };
const scheduler = new FrameScheduler({ targetFps: 30, maxInFlight: 1, inFlightTimeoutMs: 1000 });
let ws: WebSocket | null = null;
let wsUrl: string | null = null;
let wantConnection = false;
let reconnectDelay = 500;
let sessionId: string | null = null;
let source: SourceDescriptor | null = null;
let reader: ReadableStreamDefaultReader<VideoFrame> | null = null;
let running = false;
let frameId = 0;
let lastSize: { w: number; h: number } | null = null;

/** In-flight frames. `bitmap` resolves to the display copy of the exact frame analyzed. */
const pending = new Map<number, { bitmap: Promise<ImageBitmap | null>; acquired: number }>();
const captureRate = new RateMeter(2000);
const sentRate = new RateMeter(2000);
const resultRate = new RateMeter(2000);
const rtt = new RollingWindow(10_000);
const e2e = new RollingWindow(10_000);
const prep = new RollingWindow(10_000);
const counts: Record<string, number> = { errors: 0, dropped_by_engine: 0 };

let fullCanvas: OffscreenCanvas | null = null;
let fullCtx: OffscreenCanvasRenderingContext2D | null = null;
let centerCanvas: OffscreenCanvas | null = null;
let centerCtx: OffscreenCanvasRenderingContext2D | null = null;

function canvas(w: number, h: number, which: "full" | "center"): OffscreenCanvasRenderingContext2D {
  let c = which === "full" ? fullCanvas : centerCanvas;
  let ctx = which === "full" ? fullCtx : centerCtx;
  if (!c || !ctx || c.width !== w || c.height !== h) {
    c = new OffscreenCanvas(w, h);
    // GPU-backed canvas: the downscale happens on the GPU and only the small result is read back.
    ctx = c.getContext("2d", { willReadFrequently: false, alpha: false }) as OffscreenCanvasRenderingContext2D;
    ctx.imageSmoothingQuality = "high";
    if (which === "full") [fullCanvas, fullCtx] = [c, ctx];
    else [centerCanvas, centerCtx] = [c, ctx];
  }
  return ctx;
}

function setReady(): void {
  scheduler.connected = ws?.readyState === WebSocket.OPEN && sessionId !== null && running;
}

function releasePending(): void {
  for (const p of pending.values()) void p.bitmap.then((b) => b?.close());
  pending.clear();
  scheduler.reset();
}

function connect(): void {
  if (!wsUrl || !wantConnection) return;
  post({ type: "status", ws: "connecting" });
  const socket = new WebSocket(wsUrl);
  ws = socket;
  socket.onopen = () => {
    reconnectDelay = 500;
    post({ type: "status", ws: "open" });
    setReady();
  };
  socket.onclose = (ev) => {
    if (ws !== socket) return;
    ws = null;
    sessionId = null;
    releasePending();
    setReady();
    post({ type: "status", ws: "disconnected", detail: `closed (${ev.code})` });
    if (wantConnection) {
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(5000, reconnectDelay * 2);
    }
  };
  socket.onerror = () => undefined; // onclose follows with the code
  socket.onmessage = (ev) => {
    if (typeof ev.data !== "string") return;
    const msg = parseEngineMessage(ev.data);
    if (!msg) {
      post({ type: "error", message: "unrecognized engine message" });
      return;
    }
    const now = performance.now();
    switch (msg.type) {
      case "frame_result": {
        const id = msg.perception.frame_id;
        const rttMs = scheduler.markDone(id, now);
        if (rttMs !== undefined) rtt.push(rttMs, now);
        resultRate.mark(now);
        const p = pending.get(id);
        pending.delete(id);
        const received = epochMs();
        e2e.push(received - msg.perception.acquired_ts_ms, now);
        // Pair the result with its own frame (the bitmap is normally ready long before the result).
        void (p?.bitmap ?? Promise.resolve(null)).then((bitmap) =>
          post({ type: "result", message: msg, bitmap, receivedTs: received }, bitmap ? [bitmap] : []),
        );
        break;
      }
      case "frame_dropped": {
        counts.dropped_by_engine = (counts.dropped_by_engine ?? 0) + 1;
        if (msg.frame_id !== null && msg.frame_id !== undefined) {
          scheduler.markDone(msg.frame_id, now);
          void pending.get(msg.frame_id)?.bitmap.then((b) => b?.close());
          pending.delete(msg.frame_id);
        }
        post({ type: "dropped", message: msg });
        break;
      }
      case "session_started":
        sessionId = msg.session_id;
        setReady();
        post({ type: "engine", message: msg });
        break;
      case "session_ended":
        if (msg.session_id === sessionId) sessionId = null;
        releasePending();
        setReady();
        post({ type: "engine", message: msg });
        break;
      default:
        post({ type: "engine", message: msg });
    }
  };
}

async function pump(readable: ReadableStream<VideoFrame>): Promise<void> {
  reader = readable.getReader();
  try {
    while (running) {
      const { value: frame, done } = await reader.read();
      if (done || !frame) break;
      const now = performance.now();
      captureRate.mark(now);
      for (const id of scheduler.expire(now)) {
        void pending.get(id)?.bitmap.then((b) => b?.close());
        pending.delete(id);
      }
      if (scheduler.offer(now) !== "send") {
        frame.close();
        continue;
      }
      try {
        await sendFrame(frame, now);
      } catch (err) {
        counts.errors = (counts.errors ?? 0) + 1;
        try {
          frame.close();
        } catch {
          /* already closed */
        }
        post({ type: "error", message: `frame preparation failed: ${String(err)}` });
      }
    }
  } finally {
    running = false;
    setReady();
    post({ type: "capture-ended", reason: "stream ended" });
  }
}

let copyToCrop = true; // VideoFrame.copyTo with RGBA conversion; disabled if the runtime rejects it

async function centerPixels(frame: VideoFrame, c: { x: number; y: number; w: number; h: number }): Promise<Uint8Array | Uint8ClampedArray> {
  if (copyToCrop) {
    try {
      const out = new Uint8Array(c.w * c.h * 4);
      await frame.copyTo(out, { rect: { x: c.x, y: c.y, width: c.w, height: c.h }, format: "RGBA", colorSpace: "srgb" } as VideoFrameCopyToOptions);
      return out;
    } catch {
      copyToCrop = false; // fall back to the canvas path for this runtime
    }
  }
  const cctx = canvas(c.w, c.h, "center");
  cctx.drawImage(frame, c.x, c.y, c.w, c.h, 0, 0, c.w, c.h);
  return cctx.getImageData(0, 0, c.w, c.h).data;
}

async function sendFrame(frame: VideoFrame, now: number): Promise<void> {
  const acquired = epochMs();
  const w = frame.displayWidth;
  const h = frame.displayHeight;
  lastSize = { w, h };
  const a = analysisSize(w, h, config.analysisHeight);
  const fctx = canvas(a.width, a.height, "full");
  fctx.drawImage(frame, 0, 0, a.width, a.height);
  const full = fctx.getImageData(0, 0, a.width, a.height);
  const c0 = centerRect(w, h, config.centerSize);
  // Even-aligned crop origin (required by subsampled pixel formats such as I420/NV12).
  const c = { x: c0.x & ~1, y: c0.y & ~1, w: c0.w, h: c0.h };
  const center = await centerPixels(frame, c);
  const socket = ws;
  if (!socket || socket.readyState !== WebSocket.OPEN || !sessionId || !source) {
    frame.close();
    return;
  }
  const id = ++frameId;
  const packet = encodeFramePacket(
    {
      session_id: sessionId,
      frame_id: id,
      source_id: source.sourceId,
      source_kind: source.sourceKind,
      source_label: source.label,
      acquired_ts_ms: acquired,
      sent_ts_ms: epochMs(),
      source_width: w,
      source_height: h,
      simulated: false,
    },
    [
      { name: "full", srcRect: { x: 0, y: 0, w, h }, width: a.width, height: a.height, data: full.data },
      { name: "center", srcRect: c, width: c.w, height: c.h, data: center },
    ],
  );
  socket.send(packet);
  scheduler.markSent(id, now);
  sentRate.mark(now);
  prep.push(performance.now() - now, now);
  // The display bitmap is made after sending, so it never delays analysis.
  const d = displaySize(w, h, config.displayMaxWidth);
  const bitmap = config.keepBitmaps
    ? createImageBitmap(frame, { resizeWidth: d.width, resizeHeight: d.height, resizeQuality: "medium" }).catch(() => null)
    : Promise.resolve(null);
  pending.set(id, { bitmap, acquired });
  await bitmap;
  frame.close();
}

setInterval(() => {
  const now = performance.now();
  const stats: ClientStats = {
    ts: epochMs(),
    captureFps: round(captureRate.rate(now)),
    sentFps: round(sentRate.rate(now)),
    resultFps: round(resultRate.rate(now)),
    sourceWidth: lastSize?.w ?? null,
    sourceHeight: lastSize?.h ?? null,
    inFlight: scheduler.inFlightCount,
    rttMs: rtt.summary(now),
    endToEndMs: e2e.summary(now),
    prepareMs: prep.summary(now),
    counts: { ...scheduler.counts, ...counts },
  };
  post({ type: "stats", stats });
}, 1000);

function round(v: number): number {
  return Math.round(v * 10) / 10;
}

self.onmessage = (ev: MessageEvent<WorkerIn>) => {
  const msg = ev.data;
  switch (msg.type) {
    case "connect":
      wsUrl = msg.url;
      wantConnection = true;
      if (!ws) connect();
      break;
    case "disconnect":
      wantConnection = false;
      ws?.close(1000);
      break;
    case "start":
      config = { ...config, ...msg.config };
      scheduler.configure({ targetFps: config.targetFps, maxInFlight: config.maxInFlight });
      source = msg.source;
      running = true;
      frameId = 0;
      setReady();
      {
        let readable = msg.readable;
        if (!readable && msg.track) {
          const Processor = (self as unknown as { MediaStreamTrackProcessor?: new (i: { track: MediaStreamTrack; maxBufferSize?: number }) => { readable: ReadableStream<VideoFrame> } }).MediaStreamTrackProcessor;
          if (Processor) readable = new Processor({ track: msg.track, maxBufferSize: 1 }).readable;
        }
        if (!readable) {
          running = false;
          post({ type: "error", message: "MediaStreamTrackProcessor is not available in this runtime" });
          post({ type: "capture-ended", reason: "unsupported" });
          break;
        }
        void pump(readable);
      }
      break;
    case "configure":
      config = { ...config, ...msg.config };
      scheduler.configure({ targetFps: config.targetFps, maxInFlight: config.maxInFlight });
      break;
    case "control":
      if (ws?.readyState === WebSocket.OPEN) ws.send(msg.payload);
      else post({ type: "error", message: "engine not connected; control message not sent" });
      break;
    case "stop":
      running = false;
      void reader?.cancel().catch(() => undefined);
      releasePending();
      setReady();
      break;
  }
};
