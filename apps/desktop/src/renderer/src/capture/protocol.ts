/** Messages between the renderer main thread and the frame-pump worker. */
import type { EngineMessage, FrameDroppedMessage, FrameResultMessage } from "@tari/shared-types";
import type { LatencySummary } from "@tari/telemetry";

export interface SourceDescriptor {
  sourceId: string;
  sourceKind: "screen" | "window" | "video_file";
  label: string;
}

export interface PumpConfig {
  targetFps: number;
  maxInFlight: number;
  analysisHeight: number;
  centerSize: number;
  keepBitmaps: boolean;
  displayMaxWidth: number;
}

export type WorkerIn =
  | { type: "connect"; url: string }
  | { type: "disconnect" }
  | { type: "start"; readable?: ReadableStream<VideoFrame>; track?: MediaStreamTrack; source: SourceDescriptor; config: PumpConfig }
  | { type: "configure"; config: Partial<PumpConfig> }
  | { type: "control"; payload: string }
  | { type: "stop" };

export interface ClientStats {
  ts: number;
  captureFps: number;
  sentFps: number;
  resultFps: number;
  sourceWidth: number | null;
  sourceHeight: number | null;
  inFlight: number;
  rttMs: LatencySummary;
  endToEndMs: LatencySummary;
  prepareMs: LatencySummary;
  counts: Record<string, number>;
}

export type WsStatus = "disconnected" | "connecting" | "open";

export type WorkerOut =
  | { type: "status"; ws: WsStatus; detail?: string }
  | { type: "engine"; message: EngineMessage }
  | { type: "result"; message: FrameResultMessage; bitmap: ImageBitmap | null; receivedTs: number }
  | { type: "dropped"; message: FrameDroppedMessage }
  | { type: "stats"; stats: ClientStats }
  | { type: "capture-ended"; reason: string }
  | { type: "error"; message: string };
