import { describe, expect, it } from "vitest";
import type { VoiceInstruction } from "@tari/shared-types";
import { VoiceController, type SpeechEngine, type Utterance } from "../src/renderer/src/voice/voice-controller";

class FakeSpeech implements SpeechEngine {
  spoken: string[] = [];
  cancels = 0;
  handlers: { onstart(): void; onend(): void } | null = null;
  speak(u: Utterance, h: { onstart(): void; onend(): void; onerror(e: string): void }): void {
    this.spoken.push(u.text);
    this.handlers = h;
    h.onstart();
  }
  cancel(): void {
    this.cancels++;
  }
  finish(): void {
    this.handlers?.onend();
  }
}

let t = 1000;
const clock = () => t;
const v = (text: string, priority: VoiceInstruction["priority"], key = text, ttl = 4000, interrupt = false): VoiceInstruction => ({
  schema_version: "1.0.0",
  voice_id: text,
  session_id: "s",
  created_ts_ms: t,
  priority,
  domain: "aim",
  text,
  language: "en",
  dedupe_key: key,
  interrupt,
  ttl_ms: ttl,
  rec_id: null,
});

const opts = { enabled: true, voiceURI: null, rate: 1, volume: 1, cooldownMs: 8000, maxQueue: 4 };

describe("VoiceController", () => {
  it("queues by priority and plays in order", () => {
    t = 1000;
    const s = new FakeSpeech();
    const c = new VoiceController(s, opts, clock);
    expect(c.enqueue(v("p2-a", "P2"))).toBe("speaking");
    expect(c.enqueue(v("p3", "P3"))).toBe("queued");
    expect(c.enqueue(v("p2-b", "P2"))).toBe("queued");
    s.finish();
    s.finish();
    expect(s.spoken).toEqual(["p2-a", "p2-b", "p3"]);
  });

  it("P1 interrupts P2; P0 interrupts anything", () => {
    t = 1000;
    const s = new FakeSpeech();
    const c = new VoiceController(s, opts, clock);
    c.enqueue(v("explain", "P2"));
    expect(c.enqueue(v("raise placement", "P1"))).toBe("interrupted");
    expect(c.enqueue(v("engine down", "P0", "sys", 4000, true))).toBe("interrupted");
    expect(s.cancels).toBe(2);
    expect(c.enqueue(v("another p1", "P1"))).toBe("queued"); // P1 does not interrupt P0
  });

  it("suppresses duplicates within the cooldown", () => {
    t = 1000;
    const s = new FakeSpeech();
    const c = new VoiceController(s, opts, clock);
    c.enqueue(v("low", "P1", "aim.placement.low"));
    s.finish();
    t = 3000;
    expect(c.enqueue(v("low again", "P1", "aim.placement.low"))).toBe("dropped_duplicate");
    t = 9500;
    expect(c.enqueue(v("low later", "P1", "aim.placement.low"))).toBe("speaking");
  });

  it("drops stale instructions instead of speaking late", () => {
    t = 1000;
    const s = new FakeSpeech();
    const c = new VoiceController(s, opts, clock);
    const old = v("old", "P1", "old", 500);
    t = 2000;
    expect(c.enqueue(old)).toBe("dropped_expired");
    t = 2000;
    c.enqueue(v("long", "P2"));
    c.enqueue(v("short-lived", "P3", "sl", 300));
    t = 2600;
    s.finish();
    expect(s.spoken).toEqual(["long"]);
    expect(c.counts.expired).toBe(2);
  });

  it("records latency from source frame to speech start and respects disable", () => {
    t = 1000;
    const s = new FakeSpeech();
    const c = new VoiceController(s, opts, clock);
    const instr = v("x", "P1");
    t = 1350;
    c.enqueue(instr);
    expect(c.latency.summary(t).p50).toBe(350);
    c.configure({ enabled: false });
    expect(c.enqueue(v("y", "P1"))).toBe("dropped_disabled");
  });
});
