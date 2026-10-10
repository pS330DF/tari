/** Client-side rolling telemetry (time-windowed samples, percentiles, rates). */

export interface LatencySummary {
  count: number;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  mean: number | null;
  max: number | null;
}

/** Percentile with linear interpolation (matches numpy's default). */
export function percentile(sorted: number[], q: number): number | null {
  if (sorted.length === 0) return null;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  const a = sorted[lo]!;
  const b = sorted[hi]!;
  return a + (b - a) * (pos - lo);
}

export function summarize(values: number[]): LatencySummary {
  if (values.length === 0) return { count: 0, p50: null, p95: null, p99: null, mean: null, max: null };
  const sorted = [...values].sort((x, y) => x - y);
  const sum = sorted.reduce((s, v) => s + v, 0);
  const r = (v: number | null) => (v === null ? null : Math.round(v * 1000) / 1000);
  return {
    count: sorted.length,
    p50: r(percentile(sorted, 0.5)),
    p95: r(percentile(sorted, 0.95)),
    p99: r(percentile(sorted, 0.99)),
    mean: r(sum / sorted.length),
    max: r(sorted[sorted.length - 1]!),
  };
}

/** Samples kept for a sliding time window. */
export class RollingWindow {
  private ts: number[] = [];
  private vs: number[] = [];
  constructor(private readonly windowMs: number) {}

  push(value: number, now: number): void {
    this.ts.push(now);
    this.vs.push(value);
    this.prune(now);
  }

  prune(now: number): void {
    const cutoff = now - this.windowMs;
    let i = 0;
    while (i < this.ts.length && this.ts[i]! < cutoff) i++;
    if (i > 0) {
      this.ts.splice(0, i);
      this.vs.splice(0, i);
    }
  }

  values(now: number): number[] {
    this.prune(now);
    return this.vs.slice();
  }

  summary(now: number): LatencySummary {
    return summarize(this.values(now));
  }
}

/** Event rate (events/s) over a sliding window. */
export class RateMeter {
  private marks: number[] = [];
  constructor(private readonly windowMs: number) {}

  mark(now: number): void {
    this.marks.push(now);
    const cutoff = now - this.windowMs;
    while (this.marks.length && this.marks[0]! < cutoff) this.marks.shift();
  }

  rate(now: number): number {
    const cutoff = now - this.windowMs;
    while (this.marks.length && this.marks[0]! < cutoff) this.marks.shift();
    if (this.marks.length < 2) return 0;
    const span = (this.marks[this.marks.length - 1]! - this.marks[0]!) / 1000;
    return span > 0 ? (this.marks.length - 1) / span : 0;
  }
}

/** Wall-clock epoch ms with sub-ms precision (same clock the engine uses). */
export function epochMs(): number {
  return performance.timeOrigin + performance.now();
}
