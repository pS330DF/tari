import { describe, expect, it } from "vitest";
import { RateMeter, RollingWindow, percentile, summarize } from "../src";

describe("telemetry", () => {
  it("percentiles match numpy linear interpolation", () => {
    const v = Array.from({ length: 100 }, (_, i) => i + 1);
    const s = summarize(v);
    expect(s.p50).toBeCloseTo(50.5);
    expect(s.p95).toBeCloseTo(95.05);
    expect(s.p99).toBeCloseTo(99.01);
    expect(s.max).toBe(100);
    expect(percentile([], 0.5)).toBeNull();
  });
  it("rolling window drops old samples", () => {
    const w = new RollingWindow(1000);
    w.push(5, 0);
    w.push(7, 500);
    expect(w.summary(900).count).toBe(2);
    expect(w.summary(1400).count).toBe(1);
  });
  it("rate meter", () => {
    const r = new RateMeter(1000);
    for (let i = 0; i <= 30; i++) r.mark(i * 33.333);
    expect(r.rate(1000)).toBeCloseTo(30, 0);
  });
});
