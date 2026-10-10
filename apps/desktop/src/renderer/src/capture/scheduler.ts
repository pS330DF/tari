/**
 * Client-side frame scheduler.
 *
 * Bounds latency instead of throughput: a frame is only sent when fewer than
 * `maxInFlight` frames await results, and at most `targetFps` per second.
 * Everything else is skipped at the source (and closed immediately) rather
 * than queued. In-flight frames that never get an answer expire.
 */
export type OfferDecision = "send" | "skip_rate" | "skip_backpressure" | "skip_disconnected";

export interface SchedulerOptions {
  targetFps: number;
  maxInFlight: number;
  inFlightTimeoutMs: number;
}

export class FrameScheduler {
  private inFlight = new Map<number, number>();
  private lastSent = -Infinity;
  connected = false;
  readonly counts = { offered: 0, sent: 0, skip_rate: 0, skip_backpressure: 0, skip_disconnected: 0, expired: 0, completed: 0 };

  constructor(private opts: SchedulerOptions) {}

  configure(opts: Partial<SchedulerOptions>): void {
    this.opts = { ...this.opts, ...opts };
  }

  get inFlightCount(): number {
    return this.inFlight.size;
  }

  offer(now: number): OfferDecision {
    this.counts.offered++;
    this.expire(now);
    let d: OfferDecision = "send";
    if (!this.connected) d = "skip_disconnected";
    else if (this.inFlight.size >= this.opts.maxInFlight) d = "skip_backpressure";
    // Allow a little jitter (10%) so a 60 Hz source reliably yields 30 Hz at targetFps=30.
    else if (now - this.lastSent < (1000 / this.opts.targetFps) * 0.9) d = "skip_rate";
    if (d !== "send") this.counts[d]++;
    return d;
  }

  markSent(frameId: number, now: number): void {
    this.inFlight.set(frameId, now);
    this.lastSent = now;
    this.counts.sent++;
  }

  /** Returns round-trip time if the frame was in flight. */
  markDone(frameId: number, now: number): number | undefined {
    const sent = this.inFlight.get(frameId);
    if (sent === undefined) return undefined;
    this.inFlight.delete(frameId);
    this.counts.completed++;
    return now - sent;
  }

  expire(now: number): number[] {
    const expired: number[] = [];
    for (const [id, sent] of this.inFlight) {
      if (now - sent > this.opts.inFlightTimeoutMs) {
        this.inFlight.delete(id);
        expired.push(id);
      }
    }
    this.counts.expired += expired.length;
    return expired;
  }

  reset(): void {
    this.inFlight.clear();
    this.lastSent = -Infinity;
  }
}
