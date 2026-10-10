import { describe, expect, it } from "vitest";
import { FrameScheduler } from "../src/renderer/src/capture/scheduler";
import { analysisSize, centerRect } from "../src/renderer/src/capture/regions";

describe("FrameScheduler", () => {
  it("never exceeds maxInFlight and skips instead of queueing", () => {
    const s = new FrameScheduler({ targetFps: 60, maxInFlight: 1, inFlightTimeoutMs: 1000 });
    s.connected = true;
    expect(s.offer(0)).toBe("send");
    s.markSent(1, 0);
    expect(s.offer(20)).toBe("skip_backpressure");
    expect(s.offer(40)).toBe("skip_backpressure");
    expect(s.markDone(1, 45)).toBe(45);
    expect(s.offer(50)).toBe("send");
    expect(s.counts.skip_backpressure).toBe(2);
  });

  it("caps the send rate at targetFps from a faster source", () => {
    const s = new FrameScheduler({ targetFps: 30, maxInFlight: 3, inFlightTimeoutMs: 1000 });
    s.connected = true;
    let sent = 0;
    for (let i = 0; i < 120; i++) {
      const t = i * (1000 / 60);
      if (s.offer(t) === "send") {
        s.markSent(i, t);
        s.markDone(i, t + 1);
        sent++;
      }
    }
    expect(sent).toBeGreaterThanOrEqual(59);
    expect(sent).toBeLessThanOrEqual(61);
  });

  it("expires lost frames so a dropped result cannot stall the pipeline", () => {
    const s = new FrameScheduler({ targetFps: 30, maxInFlight: 1, inFlightTimeoutMs: 500 });
    s.connected = true;
    s.markSent(7, 0);
    expect(s.offer(100)).toBe("skip_backpressure");
    expect(s.offer(600)).toBe("send");
    expect(s.counts.expired).toBe(1);
    expect(s.markDone(7, 700)).toBeUndefined();
  });

  it("skips while disconnected", () => {
    const s = new FrameScheduler({ targetFps: 30, maxInFlight: 1, inFlightTimeoutMs: 500 });
    expect(s.offer(0)).toBe("skip_disconnected");
  });
});

describe("analysis regions (must match the Python generator)", () => {
  it.each([
    [1920, 1080, 960, 540],
    [2560, 1080, 1280, 540],
    [3440, 1440, 1280, 536],
    [1280, 720, 960, 540],
    [800, 450, 800, 450],
  ])("%ix%i -> %ix%i", (w, h, ew, eh) => {
    expect(analysisSize(w, h)).toEqual({ width: ew, height: eh });
  });
  it("center crop is centered and clamped", () => {
    expect(centerRect(1920, 1080)).toEqual({ x: 768, y: 348, w: 384, h: 384 });
    expect(centerRect(300, 200)).toEqual({ x: 50, y: 0, w: 200, h: 200 });
  });
});
