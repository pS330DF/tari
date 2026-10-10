/**
 * Voice output controller: priority queue with interruption and duplicate suppression.
 *
 * P0 (system/safety) interrupts anything; P1 (essential training feedback)
 * interrupts P2/P3; otherwise utterances queue by priority. An instruction
 * that cannot start within its TTL is discarded (stale feedback is worse than
 * silence). The same dedupe key is not spoken twice within the cooldown.
 */
import type { VoiceInstruction } from "@tari/shared-types";
import { RollingWindow } from "@tari/telemetry";

export interface Utterance {
  text: string;
  lang: string;
  voiceURI: string | null;
  rate: number;
  volume: number;
}

export interface SpeechEngine {
  speak(u: Utterance, handlers: { onstart(): void; onend(): void; onerror(err: string): void }): void;
  cancel(): void;
}

export type EnqueueResult = "speaking" | "queued" | "interrupted" | "dropped_disabled" | "dropped_duplicate" | "dropped_expired";

const RANK: Record<string, number> = { P0: 0, P1: 1, P2: 2, P3: 3 };
const LANG: Record<string, string> = { en: "en-US", ko: "ko-KR" };

export interface VoiceOptions {
  enabled: boolean;
  voiceURI: string | null;
  rate: number;
  volume: number;
  cooldownMs: number;
  maxQueue: number;
}

export class VoiceController {
  private queue: VoiceInstruction[] = [];
  private current: VoiceInstruction | null = null;
  private lastSpoken = new Map<string, number>();
  readonly latency = new RollingWindow(60_000);
  readonly counts = { spoken: 0, interrupted: 0, duplicate: 0, expired: 0, errors: 0 };
  onSpeakingChange: (speaking: boolean, text: string | null) => void = () => undefined;

  constructor(private engine: SpeechEngine, private opts: VoiceOptions, private now: () => number = () => Date.now()) {}

  configure(opts: Partial<VoiceOptions>): void {
    this.opts = { ...this.opts, ...opts };
    if (!this.opts.enabled) this.stopAll();
  }

  get speaking(): boolean {
    return this.current !== null;
  }

  get pending(): number {
    return this.queue.length;
  }

  enqueue(instr: VoiceInstruction): EnqueueResult {
    if (!this.opts.enabled) return "dropped_disabled";
    const now = this.now();
    if (now - instr.created_ts_ms > instr.ttl_ms) {
      this.counts.expired++;
      return "dropped_expired";
    }
    const last = this.lastSpoken.get(instr.dedupe_key);
    const duplicateQueued = this.queue.some((q) => q.dedupe_key === instr.dedupe_key) || this.current?.dedupe_key === instr.dedupe_key;
    if (duplicateQueued || (last !== undefined && now - last < this.opts.cooldownMs)) {
      this.counts.duplicate++;
      return "dropped_duplicate";
    }
    if (this.current) {
      const cur = RANK[this.current.priority] ?? 3;
      const next = RANK[instr.priority] ?? 3;
      const interrupts = next === 0 || (next === 1 && cur >= 2) || (instr.interrupt && next < cur);
      if (interrupts) {
        this.counts.interrupted++;
        this.current = null;
        this.engine.cancel();
        this.start(instr);
        return "interrupted";
      }
      this.queue.push(instr);
      this.queue.sort((a, b) => (RANK[a.priority] ?? 3) - (RANK[b.priority] ?? 3) || a.created_ts_ms - b.created_ts_ms);
      if (this.queue.length > this.opts.maxQueue) this.queue.pop();
      return "queued";
    }
    this.start(instr);
    return "speaking";
  }

  stopAll(): void {
    this.queue = [];
    if (this.current) {
      this.current = null;
      this.engine.cancel();
      this.onSpeakingChange(false, null);
    }
  }

  private start(instr: VoiceInstruction): void {
    this.current = instr;
    this.lastSpoken.set(instr.dedupe_key, this.now());
    const utterance: Utterance = {
      text: instr.text,
      lang: LANG[instr.language] ?? "en-US",
      voiceURI: this.opts.voiceURI,
      rate: this.opts.rate,
      volume: this.opts.volume,
    };
    this.engine.speak(utterance, {
      onstart: () => {
        const t = this.now();
        this.latency.push(t - instr.created_ts_ms, t);
        this.counts.spoken++;
        this.onSpeakingChange(true, instr.text);
      },
      onend: () => this.finish(instr),
      onerror: () => {
        this.counts.errors++;
        this.finish(instr);
      },
    });
  }

  private finish(instr: VoiceInstruction): void {
    if (this.current !== instr) return; // already interrupted
    this.current = null;
    const now = this.now();
    while (this.queue.length) {
      const next = this.queue.shift()!;
      if (now - next.created_ts_ms <= next.ttl_ms) {
        this.start(next);
        return;
      }
      this.counts.expired++;
    }
    this.onSpeakingChange(false, null);
  }
}

/** Web Speech API adapter (local OS voices: SAPI on Windows, AVSpeech on macOS). */
export class BrowserSpeechEngine implements SpeechEngine {
  speak(u: Utterance, h: { onstart(): void; onend(): void; onerror(err: string): void }): void {
    const synth = window.speechSynthesis;
    const utt = new SpeechSynthesisUtterance(u.text);
    utt.lang = u.lang;
    utt.rate = u.rate;
    utt.volume = u.volume;
    const voices = synth.getVoices();
    const voice = (u.voiceURI && voices.find((v) => v.voiceURI === u.voiceURI)) || voices.find((v) => v.lang === u.lang) ||
      voices.find((v) => v.lang.startsWith(u.lang.slice(0, 2)));
    if (voice) utt.voice = voice;
    utt.onstart = () => h.onstart();
    utt.onend = () => h.onend();
    utt.onerror = (e) => (e.error === "interrupted" || e.error === "canceled" ? undefined : h.onerror(e.error));
    synth.speak(utt);
  }

  cancel(): void {
    window.speechSynthesis.cancel();
  }
}
