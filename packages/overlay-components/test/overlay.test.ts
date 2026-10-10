import { describe, expect, it } from "vitest";
import type { OverlayInstruction } from "@tari/shared-types";
import { containViewport, drawOverlays, isDrawable, toCanvas } from "../src";

const instr = (sourceTs: number, ttl = 200): OverlayInstruction => ({
  schema_version: "1.0.0",
  instruction_id: "i",
  session_id: "s",
  source_frame_id: 1,
  source_ts_ms: sourceTs,
  created_ts_ms: sourceTs + 5,
  ttl_ms: ttl,
  layer: "spatial",
  gated_by: "training_lab",
  primitives: [{ kind: "circle", style: "head", points: [{ x: 0.5, y: 0.5 }], radius: 0.01, text: null, emphasis: 1 }],
});

function fakeCtx() {
  const calls: string[] = [];
  const handler: ProxyHandler<Record<string, unknown>> = {
    get: (_t, prop: string) => {
      if (prop === "measureText") return () => ({ width: 10 });
      return (..._a: unknown[]) => calls.push(prop);
    },
    set: () => true,
  };
  return { ctx: new Proxy({}, handler) as unknown as CanvasRenderingContext2D, calls };
}

describe("overlay staleness gating", () => {
  it("live mode hides instructions older than their TTL", () => {
    expect(isDrawable(instr(1000), 1150, "live")).toBe(true);
    expect(isDrawable(instr(1000), 1250, "live")).toBe(false);
  });
  it("synced mode always draws the instruction with its own frame", () => {
    expect(isDrawable(instr(1000), 99999, "synced")).toBe(true);
  });
  it("drawOverlays counts stale skips and draws fresh ones", () => {
    const { ctx, calls } = fakeCtx();
    const vp = containViewport(800, 450, 1920, 1080);
    const stats = drawOverlays(ctx, [instr(1000), instr(1400)], vp, 1500, "live");
    expect(stats).toEqual({ drawn: 1, skippedStale: 1 });
    expect(calls).toContain("arc");
  });
});

describe("viewport mapping", () => {
  it("letterboxes and maps normalized points", () => {
    const vp = containViewport(1000, 1000, 1920, 1080);
    expect(vp.width).toBeCloseTo(1000);
    expect(vp.height).toBeCloseTo(562.5);
    expect(vp.y).toBeCloseTo(218.75);
    const [x, y] = toCanvas({ x: 0.5, y: 0.5 }, vp);
    expect(x).toBeCloseTo(500);
    expect(y).toBeCloseTo(500);
  });
});
