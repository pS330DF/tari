/**
 * Analysis region geometry (mirror of tari_synth.render.analysis_size / build_packet).
 * The full frame is scaled to a fixed height (capped in width, never upscaled)
 * and an unscaled center crop is added for crosshair precision.
 */
export interface Size {
  width: number;
  height: number;
}

export interface PixelRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function analysisSize(w: number, h: number, targetHeight = 540, maxWidth = 1280): Size {
  const scale = Math.min(1, targetHeight / h, maxWidth / w);
  return { width: Math.max(1, Math.round(w * scale)), height: Math.max(1, Math.round(h * scale)) };
}

export function centerRect(w: number, h: number, size = 384): PixelRect {
  const cs = Math.min(size, w, h);
  return { x: Math.floor((w - cs) / 2), y: Math.floor((h - cs) / 2), w: cs, h: cs };
}

export function displaySize(w: number, h: number, maxWidth = 1600): Size {
  const scale = Math.min(1, maxWidth / w);
  return { width: Math.max(1, Math.round(w * scale)), height: Math.max(1, Math.round(h * scale)) };
}
