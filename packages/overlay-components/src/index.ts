/**
 * Overlay rendering for TARI spatial instructions.
 *
 * Coordinates in instructions are normalized to the source frame. A Viewport
 * maps them into the canvas rectangle where that frame is displayed. In
 * "synced" mode the renderer draws an instruction together with the exact
 * frame it was computed from; in "live" mode it draws over newer video and
 * must hide instructions whose source frame is older than their TTL.
 */
import type { OverlayInstruction, OverlayPrimitive, Point2 } from "@tari/shared-types";

export type OverlayMode = "synced" | "live";

export interface Viewport {
  /** Displayed frame rectangle in canvas pixels. */
  x: number;
  y: number;
  width: number;
  height: number;
  /** Source frame size in pixels (for radius scaling). */
  sourceWidth: number;
  sourceHeight: number;
}

export interface OverlayTheme {
  crosshair: string;
  crosshairEstimated: string;
  target: string;
  head: string;
  guide: string;
  correction: string;
  trajectory: string;
  label: string;
  labelBg: string;
  warning: string;
  good: string;
  outline: string;
  font: string;
}

export const DEFAULT_THEME: OverlayTheme = {
  crosshair: "#5eead4",
  crosshairEstimated: "#94a3b8",
  target: "rgba(226,232,240,0.55)",
  head: "#2dd4bf",
  guide: "rgba(45,212,191,0.5)",
  correction: "#22d3ee",
  trajectory: "rgba(103,232,249,0.75)",
  label: "#e6edf3",
  labelBg: "rgba(7,10,13,0.72)",
  warning: "#f5b544",
  good: "#5eead4",
  outline: "rgba(0,0,0,0.65)",
  font: '500 12px "Inter Variable", Inter, system-ui, sans-serif',
};

/** Fit a source frame into a container keeping aspect ratio (object-fit: contain). */
export function containViewport(containerW: number, containerH: number, sourceW: number, sourceH: number): Viewport {
  const scale = Math.min(containerW / sourceW, containerH / sourceH);
  const width = sourceW * scale;
  const height = sourceH * scale;
  return { x: (containerW - width) / 2, y: (containerH - height) / 2, width, height, sourceWidth: sourceW, sourceHeight: sourceH };
}

export function toCanvas(p: Point2, vp: Viewport): [number, number] {
  return [vp.x + p.x * vp.width, vp.y + p.y * vp.height];
}

/** Age of the frame an instruction describes, relative to `nowMs` (epoch ms). */
export function instructionAgeMs(instr: OverlayInstruction, nowMs: number): number {
  return nowMs - instr.source_ts_ms;
}

/**
 * Staleness gate. Synced mode draws the instruction with its own frame, so the
 * pair is always consistent; live mode hides anything older than its TTL.
 */
export function isDrawable(instr: OverlayInstruction, nowMs: number, mode: OverlayMode): boolean {
  if (mode === "synced") return true;
  return instructionAgeMs(instr, nowMs) <= instr.ttl_ms;
}

export interface DrawStats {
  drawn: number;
  skippedStale: number;
}

export function drawOverlays(
  ctx: CanvasRenderingContext2D,
  instructions: OverlayInstruction[],
  vp: Viewport,
  nowMs: number,
  mode: OverlayMode,
  theme: OverlayTheme = DEFAULT_THEME,
): DrawStats {
  const stats: DrawStats = { drawn: 0, skippedStale: 0 };
  for (const instr of instructions) {
    if (!isDrawable(instr, nowMs, mode)) {
      stats.skippedStale++;
      continue;
    }
    for (const prim of instr.primitives) drawPrimitive(ctx, prim, vp, theme);
    stats.drawn++;
  }
  return stats;
}

function styleColor(style: OverlayPrimitive["style"], t: OverlayTheme): string {
  switch (style) {
    case "crosshair":
      return t.crosshair;
    case "crosshair_estimated":
      return t.crosshairEstimated;
    case "target":
      return t.target;
    case "head":
      return t.head;
    case "guide":
      return t.guide;
    case "correction":
      return t.correction;
    case "trajectory":
      return t.trajectory;
    case "warning":
      return t.warning;
    case "good":
      return t.good;
    default:
      return t.label;
  }
}

export function drawPrimitive(ctx: CanvasRenderingContext2D, prim: OverlayPrimitive, vp: Viewport, t: OverlayTheme): void {
  const color = styleColor(prim.style, t);
  const pts = (prim.points ?? []).map((p) => toCanvas(p, vp));
  const pxPerSource = vp.width / vp.sourceWidth;
  ctx.save();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  switch (prim.kind) {
    case "cross": {
      const [x, y] = pts[0] ?? [0, 0];
      const r = Math.max(6, (prim.radius ?? 0.007) * vp.sourceWidth * pxPerSource);
      if (prim.style === "crosshair_estimated") ctx.setLineDash([3, 3]);
      strokeWithOutline(ctx, color, t.outline, 1.5, () => {
        ctx.moveTo(x - r, y);
        ctx.lineTo(x - r * 0.35, y);
        ctx.moveTo(x + r * 0.35, y);
        ctx.lineTo(x + r, y);
        ctx.moveTo(x, y - r);
        ctx.lineTo(x, y - r * 0.35);
        ctx.moveTo(x, y + r * 0.35);
        ctx.lineTo(x, y + r);
      });
      break;
    }
    case "circle": {
      const [x, y] = pts[0] ?? [0, 0];
      const r = Math.max(3, (prim.radius ?? 0.004) * vp.sourceWidth * pxPerSource);
      strokeWithOutline(ctx, color, t.outline, 1.5, () => ctx.arc(x, y, r, 0, Math.PI * 2));
      break;
    }
    case "box": {
      const [a, b] = pts;
      if (!a || !b) break;
      const w = b[0] - a[0];
      const h = b[1] - a[1];
      const c = Math.min(8, w / 3, h / 6);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      // corner brackets instead of a full rectangle: less visual weight
      for (const [cx, cy, dx, dy] of [
        [a[0], a[1], 1, 1],
        [b[0], a[1], -1, 1],
        [a[0], b[1], 1, -1],
        [b[0], b[1], -1, -1],
      ] as const) {
        ctx.moveTo(cx + dx * c, cy);
        ctx.lineTo(cx, cy);
        ctx.lineTo(cx, cy + dy * c);
      }
      ctx.stroke();
      break;
    }
    case "hline":
    case "line": {
      const [a, b] = pts;
      if (!a || !b) break;
      if (prim.kind === "hline") ctx.setLineDash([5, 4]);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
      break;
    }
    case "arrow": {
      const [a, b] = pts;
      if (!a || !b) break;
      const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const head = Math.min(9, len * 0.35);
      strokeWithOutline(ctx, color, t.outline, 1.75, () => {
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
        ctx.moveTo(b[0], b[1]);
        ctx.lineTo(b[0] - head * Math.cos(ang - 0.45), b[1] - head * Math.sin(ang - 0.45));
        ctx.moveTo(b[0], b[1]);
        ctx.lineTo(b[0] - head * Math.cos(ang + 0.45), b[1] - head * Math.sin(ang + 0.45));
      });
      break;
    }
    case "polyline": {
      if (pts.length < 2) break;
      ctx.lineWidth = 1.5;
      for (let i = 1; i < pts.length; i++) {
        const alpha = 0.2 + (0.8 * i) / (pts.length - 1);
        ctx.globalAlpha = alpha;
        ctx.strokeStyle = color;
        ctx.beginPath();
        ctx.moveTo(pts[i - 1]![0], pts[i - 1]![1]);
        ctx.lineTo(pts[i]![0], pts[i]![1]);
        ctx.stroke();
      }
      break;
    }
    case "text": {
      const [x, y] = pts[0] ?? [0, 0];
      const text = prim.text ?? "";
      if (!text) break;
      ctx.font = t.font;
      const w = ctx.measureText(text).width;
      ctx.fillStyle = t.labelBg;
      roundRect(ctx, x - 5, y - 11, w + 10, 18, 4);
      ctx.fill();
      ctx.fillStyle = color;
      ctx.textBaseline = "middle";
      ctx.fillText(text, x, y - 2);
      break;
    }
  }
  ctx.restore();
}

function strokeWithOutline(ctx: CanvasRenderingContext2D, color: string, outline: string, width: number, path: () => void): void {
  ctx.beginPath();
  path();
  ctx.strokeStyle = outline;
  ctx.lineWidth = width + 2;
  ctx.stroke();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
