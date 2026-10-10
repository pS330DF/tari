/**
 * Autotest mode (validation only): a scripted, seeded drill driven in lockstep
 * by a test harness, with exact ground truth for every rendered frame.
 *
 * It exists so the perception pipeline can be checked against real Lab
 * rendering. It plays inside the Lab's own simulation; it never generates OS
 * input and is never active unless the page is opened with `?autotest=...`.
 */
import * as THREE from "three";
import type { Drill, DrillKind } from "./drills";
import type { Player } from "./player";
import type { Range } from "./scene";

export interface AutotestConfig {
  preset: string;
  drill: DrillKind;
  seed: number;
  durationS: number;
  fps: number;
  entryPitchDeg: number; // + = crosshair held below head height
  entryYawDeg: number; // + = crosshair held behind the cover edge
  reactionMs: number;
  flickMs: number;
  outcome: "clean" | "overshoot";
  overshootDeg: number;
  shootDelayMs: number;
  strafeAtShot: boolean;
}

const PRESETS: Record<string, Partial<AutotestConfig>> = {
  angle_hold_low: { drill: "angle_hold", entryPitchDeg: 1.4, entryYawDeg: 0.8 },
  angle_hold_good: { drill: "angle_hold", entryPitchDeg: 0.15, entryYawDeg: 0.6 },
  flick_overshoot: { drill: "flick", outcome: "overshoot", overshootDeg: 1.8 },
  flick_clean: { drill: "flick" },
};

export function parseAutotest(search: string): AutotestConfig | null {
  const q = new URLSearchParams(search);
  const preset = q.get("autotest");
  if (!preset) return null;
  const base: AutotestConfig = {
    preset, drill: "angle_hold", seed: 7, durationS: 60, fps: 30, entryPitchDeg: 0.8, entryYawDeg: 0.8, reactionMs: 230,
    flickMs: 190, outcome: "clean", overshootDeg: 1.6, shootDelayMs: 70, strafeAtShot: false,
  };
  const cfg = { ...base, ...(PRESETS[preset] ?? {}) };
  for (const k of ["seed", "durationS", "fps", "entryPitchDeg", "entryYawDeg", "reactionMs", "flickMs", "overshootDeg"] as const) {
    const v = q.get(k);
    if (v !== null && Number.isFinite(Number(v))) (cfg as Record<string, unknown>)[k] = Number(v);
  }
  return cfg;
}

/** Deterministic PRNG (mulberry32). */
export function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function minJerk(t: number): number {
  const x = Math.min(1, Math.max(0, t));
  return 10 * x ** 3 - 15 * x ** 4 + 6 * x ** 5;
}

function aimAt(eye: THREE.Vector3, p: THREE.Vector3): { yaw: number; pitch: number } {
  const d = p.clone().sub(eye);
  return { yaw: Math.atan2(-d.x, -d.z), pitch: Math.atan2(d.y, Math.hypot(d.x, d.z)) };
}

interface Move {
  from: { yaw: number; pitch: number };
  to: { yaw: number; pitch: number };
  t: number;
  dur: number;
}

export interface FrameTruth {
  frame: number;
  t_ms: number;
  viewport: { w: number; h: number; dpr: number };
  crosshair_css: { x: number; y: number };
  yaw_deg: number;
  pitch_deg: number;
  drill: DrillKind;
  ammo: number;
  timer: number;
  moving: boolean;
  bot: null | { phase: string; head_css: { x: number; y: number }; head_radius_css: number; head_visible: boolean; on_screen: boolean };
  shots: number;
  kills: number;
  headshots: number;
}

export class AutoPilot {
  private move: Move | null = null;
  private stage: "hold" | "react" | "flick" | "correct" | "settle" | "fired" = "hold";
  private stageT = 0;
  private botSeen: unknown = null;
  private refires = 0;
  private raycaster = new THREE.Raycaster();

  constructor(private cfg: AutotestConfig, private player: Player, private range: Range) {}

  private startMove(to: { yaw: number; pitch: number }, durMs: number): void {
    this.move = { from: { yaw: this.player.yaw, pitch: this.player.pitch }, to, t: 0, dur: durMs / 1000 };
  }

  private advanceMove(dt: number): boolean {
    if (!this.move) return true;
    this.move.t += dt;
    const k = minJerk(this.move.t / this.move.dur);
    this.player.yaw = this.move.from.yaw + (this.move.to.yaw - this.move.from.yaw) * k;
    this.player.pitch = this.move.from.pitch + (this.move.to.pitch - this.move.from.pitch) * k;
    if (this.move.t >= this.move.dur) {
      this.move = null;
      return true;
    }
    return false;
  }

  private headOf(pos: THREE.Vector3): THREE.Vector3 {
    return new THREE.Vector3(pos.x, pos.y + 1.6, pos.z);
  }

  /** Advance the scripted player; returns true when it fires this step. */
  update(dt: number, drill: Drill): boolean {
    const eye = this.player.camera.position;
    const bot = drill.activeBot;
    const deg = THREE.MathUtils.degToRad;
    this.advanceMove(dt);
    this.stageT += dt * 1000;
    if (!bot || !bot.alive) {
      if (this.stage !== "hold") {
        this.stage = "hold";
        this.botSeen = null;
        this.refires = 0;
      }
      const plan = drill.nextPlan;
      if (plan && !this.move) {
        const head = this.headOf(plan.to);
        let aim = aimAt(eye, head);
        if (plan.kind === "angle_hold") {
          const back = plan.from.clone().sub(plan.to).setY(0).normalize();
          const dist = eye.distanceTo(head);
          const held = head.clone().addScaledVector(back, dist * Math.tan(deg(this.cfg.entryYawDeg)));
          aim = aimAt(eye, held);
          aim.pitch -= deg(this.cfg.entryPitchDeg);
          if (Math.abs(aim.yaw - this.player.yaw) > 1e-4 || Math.abs(aim.pitch - this.player.pitch) > 1e-4) this.startMove(aim, 380);
        }
      }
      return false;
    }
    if (this.botSeen !== bot) {
      this.botSeen = bot;
      this.stage = "react";
      this.stageT = 0;
    }
    const head = this.headOf(bot.group.position);
    switch (this.stage) {
      case "react":
        if (this.stageT >= this.cfg.reactionMs + (this.cfg.drill === "angle_hold" ? 170 : 0)) {
          let target = aimAt(eye, head);
          if (this.cfg.outcome === "overshoot") {
            const dy = target.yaw - this.player.yaw;
            const dp = target.pitch - this.player.pitch;
            const mag = Math.hypot(dy, dp) || 1;
            target = { yaw: target.yaw + (dy / mag) * deg(this.cfg.overshootDeg), pitch: target.pitch + (dp / mag) * deg(this.cfg.overshootDeg) };
          }
          this.startMove(target, this.cfg.flickMs);
          this.stage = "flick";
          this.stageT = 0;
        }
        return false;
      case "flick":
        if (!this.move) {
          if (this.cfg.outcome === "overshoot") {
            this.stage = "correct";
            this.stageT = 0;
          } else {
            this.stage = "settle";
            this.stageT = 0;
          }
        }
        return false;
      case "correct":
        if (this.stageT >= 60 && !this.move) {
          this.startMove(aimAt(eye, head), 140);
          this.stage = "settle";
          this.stageT = -140;
        }
        return false;
      case "settle":
        if (!this.move) {
          // Track the (possibly still moving) head so the shot lands.
          const a = aimAt(eye, head);
          this.player.yaw = a.yaw;
          this.player.pitch = a.pitch;
        }
        if (this.stageT >= this.cfg.shootDelayMs && !this.move) {
          this.stage = "fired";
          this.stageT = 0;
          return true;
        }
        return false;
      case "fired":
        if (this.stageT >= 260 && this.refires < 2) {
          this.refires++;
          this.stage = "settle";
          this.stageT = 0;
        }
        return false;
      default:
        return false;
    }
  }

  truth(frame: number, tMs: number, drill: Drill): FrameTruth {
    const cam = this.player.camera;
    const w = window.innerWidth;
    const h = window.innerHeight;
    const toCss = (v: THREE.Vector3) => {
      const p = v.clone().project(cam);
      return { x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, z: p.z };
    };
    let bot: FrameTruth["bot"] = null;
    const b = drill.activeBot;
    if (b && b.group.visible) {
      const head = this.headOf(b.group.position);
      const c = toCss(head);
      const up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion).multiplyScalar(0.12);
      const top = toCss(head.clone().add(up));
      const eye = cam.position;
      this.raycaster.set(eye, head.clone().sub(eye).normalize());
      const blocked = this.raycaster.intersectObjects(this.range.coverMeshes(), false).some((hit) => hit.distance < eye.distanceTo(head) - 0.05);
      bot = {
        phase: b.phase,
        head_css: { x: c.x, y: c.y },
        head_radius_css: Math.hypot(top.x - c.x, top.y - c.y),
        head_visible: !blocked,
        on_screen: c.z < 1 && c.x >= 0 && c.x <= w && c.y >= 0 && c.y <= h,
      };
    }
    return {
      frame,
      t_ms: tMs,
      viewport: { w, h, dpr: window.devicePixelRatio || 1 },
      crosshair_css: { x: Math.round(w / 2), y: Math.round(h / 2) },
      yaw_deg: THREE.MathUtils.radToDeg(this.player.yaw),
      pitch_deg: THREE.MathUtils.radToDeg(this.player.pitch),
      drill: drill.kind,
      ammo: drill.ammo,
      timer: Math.ceil(drill.timeLeft),
      moving: this.player.movementError > 0.05,
      bot,
      shots: drill.result.shots,
      kills: drill.result.kills,
      headshots: drill.result.headshots,
    };
  }
}
