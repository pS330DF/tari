/**
 * 2D HUD: crosshair (with movement-error spread) and the fiducial-anchored
 * instrument cluster (drill, ammo, timer as seven-segment readouts). Layout
 * comes from the shared profile so the perception engine reads it exactly.
 */
import { profile } from "./profile";

export interface HudState {
  drill: number | null;
  ammo: number | null;
  timer: number | null;
  crosshairColor: string;
  movementError: number; // 0..1
  showCluster: boolean;
}

/** Minimal 2D context surface (lets tests record draw calls). */
export interface Ctx2D {
  fillStyle: string | CanvasGradient | CanvasPattern;
  font: string;
  textAlign: CanvasTextAlign;
  textBaseline: CanvasTextBaseline;
  fillRect(x: number, y: number, w: number, h: number): void;
  fillText(text: string, x: number, y: number): void;
  clearRect(x: number, y: number, w: number, h: number): void;
  setTransform(a: number, b: number, c: number, d: number, e: number, f: number): void;
}

export function markerSize(viewportHeight: number): number {
  return Math.max(profile.fiducial.size_css_px, profile.fiducial.size_viewport_fraction * viewportHeight);
}

/** Top-left of the marker in CSS px (bottom-left anchored cluster). */
export function markerOrigin(viewportHeight: number): { x: number; y: number; M: number } {
  const M = markerSize(viewportHeight);
  const frame = profile.hud.fiducial_frame;
  const margin = profile.fiducial.margin_css_px;
  return { x: margin - frame[0] * M, y: viewportHeight - margin - (frame[1] + frame[3]) * M, M };
}

function snap(v: number): number {
  return Math.round(v);
}

function rect(ctx: Ctx2D, ox: number, oy: number, M: number, u: number, v: number, w: number, h: number, color: string): void {
  // Snap to whole CSS pixels so edges land on device pixels (same rounding as the synthetic renderer).
  const x0 = snap(ox + u * M);
  const y0 = snap(oy + v * M);
  const x1 = snap(ox + (u + w) * M);
  const y1 = snap(oy + (v + h) * M);
  ctx.fillStyle = color;
  ctx.fillRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
}

export function drawCluster(ctx: Ctx2D, viewportHeight: number, state: HudState): void {
  const { x: ox, y: oy, M } = markerOrigin(viewportHeight);
  const hud = profile.hud;
  const c = hud.colors;
  const f = hud.fiducial_frame;
  rect(ctx, ox, oy, M, f[0], f[1], f[2], f[3], c.frame);
  const q = hud.quiet_zone;
  rect(ctx, ox, oy, M, q[0], q[1], q[2], q[3], c.quiet);
  const cells = profile.fiducial.cells;
  profile.fiducial.bits.forEach((row, j) =>
    row.forEach((bit, i) => rect(ctx, ox, oy, M, i / cells, j / cells, 1 / cells, 1 / cells, bit ? "#ffffff" : "#000000")),
  );
  const p = hud.panel;
  rect(ctx, ox, oy, M, p[0], p[1], p[2], p[3], c.panel);
  const values: Record<string, number | null> = { drill: state.drill, ammo: state.ammo, timer: state.timer };
  for (const [name, ro] of Object.entries(hud.readouts)) {
    const value = values[name];
    const text = value === null || value === undefined ? "" : String(Math.max(0, Math.floor(value))).padStart(ro.digits, "0").slice(-ro.digits);
    for (let k = 0; k < ro.digits; k++) {
      const lit = new Set(text ? hud.digit_patterns[text[k]!] ?? "" : "");
      const u0 = ro.x + k * ro.pitch;
      for (const [seg, [x0, y0, x1, y1]] of Object.entries(hud.segments)) {
        rect(ctx, ox, oy, M, u0 + x0 * ro.digit_w, ro.y + y0 * ro.digit_h, (x1 - x0) * ro.digit_w, (y1 - y0) * ro.digit_h, lit.has(seg) ? c.lit : c.unlit);
      }
    }
    ctx.fillStyle = c.label;
    ctx.font = `600 ${Math.max(8, Math.round(0.15 * M))}px Inter, system-ui, sans-serif`;
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(ro.label, ox + ro.x * M, oy + (ro.y + ro.digit_h + 0.1) * M);
  }
}

/** Crosshair arms at the exact viewport center; gap widens with movement error. */
export function crosshairArms(cx: number, cy: number, movementError: number): [number, number, number, number][] {
  const ch = profile.crosshair;
  const g = Math.round(ch.gap_css_px + Math.min(1, Math.max(0, movementError)) * ch.movement_error_max_css_px);
  const L = ch.arm_length_css_px;
  const t = ch.thickness_css_px;
  const h = Math.floor(t / 2);
  return [
    [cx - g - L, cy - h, L, t],
    [cx + g, cy - h, L, t],
    [cx - h, cy - g - L, t, L],
    [cx - h, cy + g, t, L],
  ];
}

export function drawCrosshair(ctx: Ctx2D, cx: number, cy: number, color: string, movementError: number): void {
  const arms = crosshairArms(Math.round(cx), Math.round(cy), movementError);
  ctx.fillStyle = profile.crosshair.outline;
  for (const [x, y, w, h] of arms) ctx.fillRect(x - 1, y - 1, w + 2, h + 2);
  ctx.fillStyle = color;
  for (const [x, y, w, h] of arms) ctx.fillRect(x, y, w, h);
}

export class Hud {
  private ctx: CanvasRenderingContext2D;
  constructor(private canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext("2d", { alpha: true })!;
  }

  resize(): void {
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(window.innerWidth * dpr);
    this.canvas.height = Math.round(window.innerHeight * dpr);
  }

  draw(state: HudState): void {
    const dpr = window.devicePixelRatio || 1;
    const ctx = this.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    if (state.showCluster) drawCluster(ctx, window.innerHeight, state);
    drawCrosshair(ctx, window.innerWidth / 2, window.innerHeight / 2, state.crosshairColor, state.movementError);
  }
}
