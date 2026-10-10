/**
 * Main-thread side of capture: obtains a MediaStream from the selected
 * source, hands its VideoFrame stream to the worker, and forwards worker
 * messages to subscribers.
 */
import type { CaptureSourceInfo } from "../../../shared/ipc";
import type { PumpConfig, SourceDescriptor, WorkerIn, WorkerOut } from "./protocol";

declare global {
  interface HTMLMediaElement {
    captureStream(): MediaStream;
  }
}

type ProcessorCtor = new (init: { track: MediaStreamTrack; maxBufferSize?: number }) => { readable: ReadableStream<VideoFrame> };

/** Chromium exposes MediaStreamTrackProcessor on Window; if a build only exposes it in workers,
 * the track itself is transferred and the worker constructs the processor. */
function windowProcessor(): ProcessorCtor | null {
  return (globalThis as unknown as { MediaStreamTrackProcessor?: ProcessorCtor }).MediaStreamTrackProcessor ?? null;
}

export type Listener = (msg: WorkerOut) => void;

export class CaptureController {
  private worker: Worker;
  private listeners = new Set<Listener>();
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private objectUrl: string | null = null;
  current: SourceDescriptor | null = null;

  constructor() {
    this.worker = new Worker(new URL("./frame-pump.worker.ts", import.meta.url), { type: "module" });
    this.worker.onmessage = (ev: MessageEvent<WorkerOut>) => {
      if (ev.data.type === "capture-ended") this.release();
      for (const l of this.listeners) l(ev.data);
    };
    this.worker.onerror = (ev) => {
      for (const l of this.listeners) l({ type: "error", message: `capture worker error: ${ev.message}` });
    };
  }

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  private post(msg: WorkerIn, transfer: Transferable[] = []): void {
    this.worker.postMessage(msg, transfer);
  }

  connect(url: string): void {
    this.post({ type: "connect", url });
  }

  disconnect(): void {
    this.post({ type: "disconnect" });
  }

  control(message: object): void {
    this.post({ type: "control", payload: JSON.stringify(message) });
  }

  configure(config: Partial<PumpConfig>): void {
    this.post({ type: "configure", config });
  }

  /** Live stream for the "live" viewer mode (null for video files until playing). */
  get mediaStream(): MediaStream | null {
    return this.stream;
  }

  async startDesktop(source: CaptureSourceInfo, config: PumpConfig): Promise<void> {
    const sel = await window.tari.invoke("capture:select", { id: source.id });
    if (!sel.ok) throw new Error(sel.reason ?? "Source unavailable");
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 60, max: 60 } }, audio: false });
    this.attach(stream, { sourceId: source.id, sourceKind: source.kind, label: source.name }, config);
  }

  async startFile(file: File, config: PumpConfig): Promise<void> {
    const video = document.createElement("video");
    this.objectUrl = URL.createObjectURL(file);
    video.src = this.objectUrl;
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    await video.play();
    this.video = video;
    this.attach(video.captureStream(), { sourceId: `file:${file.name}`, sourceKind: "video_file", label: file.name }, config);
  }

  private attach(stream: MediaStream, source: SourceDescriptor, config: PumpConfig): void {
    const track = stream.getVideoTracks()[0];
    if (!track) throw new Error("Source produced no video track");
    this.stream = stream;
    this.current = source;
    const Processor = windowProcessor();
    if (Processor) {
      const processor = new Processor({ track, maxBufferSize: 1 });
      this.post({ type: "start", readable: processor.readable, source, config }, [processor.readable as unknown as Transferable]);
    } else {
      this.post({ type: "start", track, source, config }, [track as unknown as Transferable]);
    }
    track.addEventListener("ended", () => this.stop());
  }

  stop(): void {
    this.post({ type: "stop" });
    this.release();
  }

  private release(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.current = null;
    if (this.video) {
      this.video.pause();
      this.video.removeAttribute("src");
      this.video = null;
    }
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }
  }
}
