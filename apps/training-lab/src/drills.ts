/**
 * Drills.
 * - Angle hold: bots peek from cover edges one at a time; train crosshair placement.
 * - Flick: bots appear at random positions in the open; train target acquisition.
 * The Lab keeps its own exact score (it knows true hits); TARI never reads it.
 */
import * as THREE from "three";
import { Bot } from "./bot";
import type { Player } from "./player";
import type { TargetColor } from "./profile";
import type { Range } from "./scene";

export type DrillKind = "angle_hold" | "flick";

export interface DrillResult {
  kind: DrillKind;
  kills: number;
  headshots: number;
  shots: number;
  bodyHits: number;
  spawned: number;
  escaped: number;
}

const MAG = 25;
const FIRE_INTERVAL_S = 0.18;
const RELOAD_S = 1.8;

export interface SpawnPlan {
  kind: DrillKind;
  /** Angle hold: hidden start and exposed stop positions (bot ground point). */
  from: THREE.Vector3;
  to: THREE.Vector3;
  holdS: number;
  /** Flick: stand position and lifetime. */
  lifetimeS: number;
}

export class Drill {
  state: "countdown" | "running" | "done" = "countdown";
  /** The next bot appearance, decided when it is scheduled (lets autotest pre-aim like a player holding an angle). */
  nextPlan: SpawnPlan | null = null;
  countdown = 3;
  timeLeft: number;
  ammo = MAG;
  reloading = 0;
  private cooldown = 0;
  private nextSpawn = 0.8;
  private lastSpot = -1;
  private readonly bots: Bot[];
  private active: Bot | null = null;
  private raycaster = new THREE.Raycaster();
  readonly result: DrillResult;

  constructor(readonly kind: DrillKind, readonly durationS: number, color: TargetColor, private range: Range,
              private rng: () => number = Math.random) {
    this.timeLeft = durationS;
    this.result = { kind, kills: 0, headshots: 0, shots: 0, bodyHits: 0, spawned: 0, escaped: 0 };
    this.bots = [new Bot(color), new Bot(color)];
    for (const b of this.bots) range.scene.add(b.group);
  }

  dispose(): void {
    for (const b of this.bots) this.range.scene.remove(b.group);
  }

  setColor(color: TargetColor): void {
    for (const b of this.bots) b.setColor(color);
  }

  update(dt: number, player: Player): void {
    if (this.state === "countdown") {
      this.countdown -= dt;
      if (this.countdown <= 0) this.state = "running";
      return;
    }
    if (this.state !== "running") return;
    this.timeLeft -= dt;
    this.cooldown = Math.max(0, this.cooldown - dt);
    if (this.reloading > 0) {
      this.reloading -= dt;
      if (this.reloading <= 0) this.ammo = MAG;
    }
    if (this.timeLeft <= 0) {
      this.timeLeft = 0;
      this.state = "done";
      for (const b of this.bots) b.group.visible = false;
      return;
    }
    if (this.active) {
      const left = this.active.update(dt);
      if (left) {
        if (this.active.phase === "hidden" && this.activeEscaped) this.result.escaped++;
        this.active = null;
        this.nextSpawn = this.kind === "angle_hold" ? 0.9 + this.rng() * 1.1 : 0.35 + this.rng() * 0.45;
        this.nextPlan = this.plan(player);
      }
    } else {
      if (!this.nextPlan) this.nextPlan = this.plan(player);
      this.nextSpawn -= dt;
      if (this.nextSpawn <= 0) this.spawn(player);
    }
  }

  private activeEscaped = true;

  /** Decide where the next bot appears. */
  plan(player: Player): SpawnPlan | null {
    const rng = this.rng;
    if (this.kind === "angle_hold") {
      const spots = this.range.peekSpots;
      let i = Math.floor(rng() * spots.length);
      if (i === this.lastSpot) i = (i + 1) % spots.length;
      this.lastSpot = i;
      const s = spots[i]!;
      return {
        kind: "angle_hold",
        from: new THREE.Vector3(s.edgeX - s.dir * 0.9, s.groundY, s.z),
        to: new THREE.Vector3(s.edgeX + s.dir * (0.9 + rng() * 0.9), s.groundY, s.z),
        holdS: 0.7 + rng() * 0.7,
        lifetimeS: 0,
      };
    }
    const eye = player.camera.position;
    for (let attempt = 0; attempt < 30; attempt++) {
      const yaw = player.yaw + THREE.MathUtils.degToRad((rng() * 2 - 1) * 38);
      const dist = 8 + rng() * 16;
      const pos = new THREE.Vector3(eye.x - Math.sin(yaw) * dist, 0, eye.z - Math.cos(yaw) * dist);
      if (pos.z > -4 || Math.abs(pos.x) > 27 || pos.z < -68) continue;
      const head = pos.clone().setY(1.6);
      this.raycaster.set(eye, head.clone().sub(eye).normalize());
      const blocked = this.raycaster.intersectObjects(this.range.coverMeshes(), false).some((h) => h.distance < eye.distanceTo(head));
      if (blocked) continue;
      return { kind: "flick", from: pos, to: pos.clone(), holdS: 0, lifetimeS: 1.6 };
    }
    return null;
  }

  private spawn(player: Player): void {
    const plan = this.nextPlan ?? this.plan(player);
    this.nextPlan = null;
    if (!plan) return;
    const bot = this.bots[this.result.spawned % this.bots.length]!;
    this.activeEscaped = true;
    if (plan.kind === "angle_hold") bot.peek(plan.from, plan.to, 5.5, plan.holdS);
    else bot.stand(plan.from, plan.lifetimeS);
    this.active = bot;
    this.result.spawned++;
  }

  /** The bot currently in play (for ground-truth export). */
  get activeBot(): Bot | null {
    return this.active;
  }

  /** Fire one shot along `ray`. Returns what was hit. */
  fire(ray: THREE.Ray): "kill" | "hit" | "miss" | "empty" | "cooldown" {
    if (this.state !== "running") return "cooldown";
    if (this.reloading > 0 || this.cooldown > 0) return "cooldown";
    if (this.ammo <= 0) {
      this.reload();
      return "empty";
    }
    this.ammo--;
    this.cooldown = FIRE_INTERVAL_S;
    this.result.shots++;
    if (this.ammo === 0) this.reload();
    const bot = this.active;
    if (!bot || !bot.alive) return "miss";
    this.raycaster.set(ray.origin, ray.direction);
    const targets = [bot.head, ...bot.body, ...this.range.coverMeshes()];
    const hits = this.raycaster.intersectObjects(targets, false);
    const first = hits[0];
    if (!first) return "miss";
    if (first.object === bot.head || bot.body.includes(first.object)) {
      const isHead = first.object === bot.head;
      const r = bot.hit(isHead);
      if (r === "kill") {
        this.activeEscaped = false;
        this.result.kills++;
        if (isHead) this.result.headshots++;
      } else {
        this.result.bodyHits++;
      }
      return r;
    }
    return "miss";
  }

  reload(): void {
    if (this.reloading <= 0 && this.ammo < MAG) this.reloading = RELOAD_S;
  }
}
