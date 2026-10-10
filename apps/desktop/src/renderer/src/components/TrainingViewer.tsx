/**
 * Training viewer.
 *
 * Synced mode draws each analyzed frame together with the overlays computed
 * from that same frame (pixel-accurate, delayed by the processing latency).
 * Live mode shows the raw stream and draws overlays only while they are
 * younger than their TTL, so stale spatial corrections never appear current.
 */
import { DEFAULT_THEME, containViewport, drawOverlays, isDrawable } from "@tari/overlay-components";
import { epochMs } from "@tari/telemetry";
import { FlaskConical, MonitorPlay, ShieldAlert } from "lucide-react";
import { useEffect, useRef } from "react";
import { runtime } from "../runtime";
import { useApp } from "../store/app-store";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Segmented } from "./ui/segmented";

export function TrainingViewer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const settings = useApp((s) => s.settings);
  const capture = useApp((s) => s.capture);
  const live = useApp((s) => s.live.state);
  const mode = settings?.capture.viewerMode ?? "synced";

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = mode === "live" && capture.state === "running" ? runtime.capture.mediaStream : null;
    if (video.srcObject) void video.play().catch(() => undefined);
  }, [mode, capture.state]);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const wrap = wrapRef.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let lastDrawn = -1;
    let dirty = true;
    const resize = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(wrap.clientWidth * dpr);
      canvas.height = Math.round(wrap.clientHeight * dpr);
      dirty = true;
    });
    resize.observe(wrap);

    const frame = () => {
      raf = requestAnimationFrame(frame);
      const bus = runtime.frameBus;
      const currentMode = useApp.getState().settings?.capture.viewerMode ?? "synced";
      const result = bus.result;
      if (currentMode === "synced" && bus.version === lastDrawn && !dirty) return;
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!result) {
        lastDrawn = bus.version;
        dirty = false;
        return;
      }
      const srcW = result.perception.source_width;
      const srcH = result.perception.source_height;
      const vp = containViewport(canvas.width / dpr, canvas.height / dpr, srcW, srcH);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const now = epochMs();
      if (currentMode === "synced") {
        if (bus.bitmap) {
          ctx.imageSmoothingQuality = "high";
          ctx.drawImage(bus.bitmap, vp.x, vp.y, vp.width, vp.height);
        }
        drawOverlays(ctx, result.overlays, vp, now, "synced", DEFAULT_THEME);
      } else {
        drawOverlays(ctx, result.overlays.filter((o) => isDrawable(o, now, "live")), vp, now, "live", DEFAULT_THEME);
      }
      if (bus.version !== lastDrawn) {
        runtime.notePresented(result);
        bus.drawnVersion = bus.version;
      }
      lastDrawn = bus.version;
      dirty = false;
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      resize.disconnect();
    };
  }, []);

  const restricted = capture.state === "running" && live?.coaching_mode === "restricted";
  const verified = live?.coaching_mode === "live_training";
  const drill = live?.drill.status === "observed" ? live.drill.value : null;

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="flex h-9 shrink-0 items-center gap-2 px-4">
        {capture.state === "running" ? (
          verified ? (
            <Badge tone="accent">Training Lab verified{drill ? ` · ${drill === "angle_hold" ? "Angle hold" : drill === "flick" ? "Flick" : drill}` : ""}</Badge>
          ) : (
            <Badge tone="warn">Source not verified</Badge>
          )
        ) : (
          <Badge>No active source</Badge>
        )}
        {live?.crosshair.status === "estimated" && capture.state === "running" && <Badge tone="warn">Crosshair not detected</Badge>}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[11.5px] text-fg-subtle">Viewer</span>
          <Segmented
            size="sm"
            value={mode}
            onChange={(v) => void window.tari.invoke("settings:set", { capture: { viewerMode: v } })}
            options={[{ value: "synced", label: "Analyzed frames" }, { value: "live", label: "Live + overlay" }]}
          />
        </div>
      </div>
      <div ref={wrapRef} className="relative mx-4 mb-3 min-h-0 flex-1 overflow-hidden rounded-md border border-line bg-[#07090b]">
        <video ref={videoRef} muted playsInline className={mode === "live" ? "absolute inset-0 h-full w-full object-contain" : "hidden"} />
        <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
        {capture.state !== "running" && capture.state !== "starting" && <EmptyState />}
        {restricted && (
          <div className="absolute inset-x-0 top-0 flex items-start gap-3 border-b border-warn/25 bg-[#17130a]/95 px-4 py-3">
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warn" />
            <div className="text-[12.5px] leading-relaxed">
              <p className="font-medium text-fg">Live coaching is paused for this source.</p>
              <p className="text-fg-muted">{live?.coaching_mode_reason}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="max-w-md text-center">
        <MonitorPlay className="mx-auto mb-3 size-6 text-fg-subtle" />
        <p className="text-[14px] font-medium text-fg">Pick a source and start a session</p>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-fg-muted">
          Live coaching runs in the TARI Training Lab, where TARI verifies the environment from its on-screen marker.
          Other sources are captured but not analyzed.
        </p>
        <Button className="mt-4" variant="secondary" onClick={() => void window.tari.invoke("lab:open", undefined)}>
          <FlaskConical /> Open Training Lab
        </Button>
      </div>
    </div>
  );
}
