import type {
  FrameDroppedMessage,
  FrameResultMessage,
  HelloMessage,
  NoticeMessage,
  PongMessage,
  SessionEndedMessage,
  SessionStartedMessage,
  TelemetryMessage,
} from "./generated";

export type EngineMessage =
  | HelloMessage
  | SessionStartedMessage
  | FrameResultMessage
  | FrameDroppedMessage
  | TelemetryMessage
  | NoticeMessage
  | SessionEndedMessage
  | PongMessage;

const ENGINE_TYPES = new Set<EngineMessage["type"]>([
  "hello",
  "session_started",
  "frame_result",
  "frame_dropped",
  "telemetry",
  "notice",
  "session_ended",
  "pong",
]);

/** Parse an engine message, rejecting unknown shapes instead of guessing. */
export function parseEngineMessage(text: string): EngineMessage | null {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object") return null;
  const type = (value as { type?: unknown }).type;
  if (typeof type !== "string" || !ENGINE_TYPES.has(type as EngineMessage["type"])) return null;
  return value as EngineMessage;
}

export function isMajorCompatible(peer: string, ours: string): boolean {
  return peer.split(".")[0] === ours.split(".")[0];
}
