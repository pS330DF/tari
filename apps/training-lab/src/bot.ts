/**
 * Training bot: an unlit humanoid in the enemy highlight color.
 * Proportions: head radius 0.12 m centered at 1.6 m above its ground, a narrow
 * neck, shoulders ~0.46 m wide — a clear head/shoulder silhouette.
 */
import * as THREE from "three";
import { profile, type TargetColor } from "./profile";

export type BotPhase = "hidden" | "emerging" | "holding" | "retreating" | "standing" | "dead";

const HEAD_R = profile.targets.head_radius_m;
const HEAD_Y = profile.targets.head_center_height_m;

export class Bot {
  readonly group = new THREE.Group();
  readonly head: THREE.Mesh;
  readonly body: THREE.Object3D[] = [];
  private material: THREE.MeshBasicMaterial;
  private baseColor: number;
  phase: BotPhase = "hidden";
  health = 2;
  private t = 0;
  private flash = 0;
  // Peek motion parameters
  private from = new THREE.Vector3();
  private to = new THREE.Vector3();
  private holdS = 1;
  private strafeS = 0.25;
  private lifetime = Infinity;
  exposedAt: number | null = null;

  constructor(color: TargetColor) {
    this.material = new THREE.MeshBasicMaterial({ color: profile.targets.colors[color], fog: false, toneMapped: false });
    this.baseColor = this.material.color.getHex();
    const m = this.material;
    this.head = new THREE.Mesh(new THREE.SphereGeometry(HEAD_R, 24, 16), m);
    this.head.position.y = HEAD_Y;
    const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.14, 12), m);
    neck.position.y = HEAD_Y - HEAD_R - 0.04;
    const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.23, 0.18, 0.56, 16), m);
    torso.position.y = HEAD_Y - HEAD_R - 0.36;
    torso.scale.z = 0.55;
    const hips = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.16, 0.2), m);
    hips.position.y = 0.92;
    const legL = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.06, 0.88, 10), m);
    legL.position.set(-0.09, 0.44, 0);
    const legR = legL.clone();
    legR.position.x = 0.09;
    this.body.push(neck, torso, hips, legL, legR);
    this.group.add(this.head, ...this.body);
    this.group.visible = false;
  }

  setColor(color: TargetColor): void {
    this.material.color.set(profile.targets.colors[color]);
    this.baseColor = this.material.color.getHex();
  }

  get alive(): boolean {
    return this.phase !== "dead" && this.phase !== "hidden";
  }

  /** Peek: strafe from behind cover to `to`, hold, then retreat. */
  peek(from: THREE.Vector3, to: THREE.Vector3, speed: number, holdS: number): void {
    this.from.copy(from);
    this.to.copy(to);
    this.strafeS = from.distanceTo(to) / speed;
    this.holdS = holdS;
    this.start("emerging", from);
  }

  stand(at: THREE.Vector3, lifetimeS: number): void {
    this.lifetime = lifetimeS;
    this.start("standing", at);
  }

  private start(phase: BotPhase, at: THREE.Vector3): void {
    this.phase = phase;
    this.t = 0;
    this.health = 2;
    this.flash = 0;
    this.exposedAt = null;
    this.group.position.copy(at);
    this.group.visible = true;
    this.material.color.setHex(this.baseColor);
  }

  /** Returns true when the bot left the field (retreated / expired / death animation done). */
  update(dt: number): boolean {
    this.t += dt;
    if (this.flash > 0) {
      this.flash -= dt;
      if (this.flash <= 0) {
        this.group.visible = false;
        this.phase = "hidden";
        this.material.color.setHex(this.baseColor);
        return true;
      }
      return false;
    }
    switch (this.phase) {
      case "emerging": {
        const k = Math.min(1, this.t / this.strafeS);
        this.group.position.lerpVectors(this.from, this.to, k);
        if (k >= 1) {
          this.phase = "holding";
          this.t = 0;
        }
        return false;
      }
      case "holding":
        if (this.t >= this.holdS) {
          this.phase = "retreating";
          this.t = 0;
        }
        return false;
      case "retreating": {
        const k = Math.min(1, this.t / this.strafeS);
        this.group.position.lerpVectors(this.to, this.from, k);
        if (k >= 1) {
          this.group.visible = false;
          this.phase = "hidden";
          return true;
        }
        return false;
      }
      case "standing":
        if (this.t >= this.lifetime) {
          this.group.visible = false;
          this.phase = "hidden";
          return true;
        }
        return false;
      default:
        return false;
    }
  }

  /** Apply a hit. Returns "kill" | "hit". Headshots kill; two body shots kill. */
  hit(isHead: boolean): "kill" | "hit" {
    this.health -= isHead ? 2 : 1;
    if (this.health <= 0) {
      this.phase = "dead";
      this.flash = 0.09; // brief white flash, then removed
      this.material.color.set("#ffffff");
      return "kill";
    }
    return "hit";
  }
}
