/** First-person controller: raw mouse look (VALORANT sensitivity scale) and WASD movement. */
import * as THREE from "three";
import { profile } from "./profile";

const RUN_SPEED = 6.75; // m/s
const WALK_SPEED = 3.3;
const ACCEL = 55;
const DECEL = 75;
const MOVING_THRESHOLD = 0.6;
export const MAX_MOVE_SPREAD_DEG = 3.0;

export class Player {
  readonly camera: THREE.PerspectiveCamera;
  yaw = 0;
  pitch = 0;
  readonly position = new THREE.Vector3(0, 0, 0);
  readonly velocity = new THREE.Vector3();
  sensitivity = 0.35; // VALORANT in-game sensitivity; degrees per count = 0.07 * sens
  private keys = new Set<string>();

  constructor() {
    this.camera = new THREE.PerspectiveCamera(70, 16 / 9, 0.05, 200);
    this.camera.rotation.order = "YXZ";
    this.resize(window.innerWidth, window.innerHeight);
    window.addEventListener("keydown", (e) => this.keys.add(e.code));
    window.addEventListener("keyup", (e) => this.keys.delete(e.code));
    window.addEventListener("blur", () => this.keys.clear());
  }

  /** Horizontal FOV is fixed (103°, like VALORANT); vertical FOV follows the aspect ratio. */
  resize(w: number, h: number): void {
    const aspect = w / h;
    const hfov = THREE.MathUtils.degToRad(profile.camera.hfov_deg);
    this.camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(hfov / 2) / aspect));
    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();
  }

  look(dx: number, dy: number): void {
    const degPerCount = 0.07 * this.sensitivity;
    this.yaw -= THREE.MathUtils.degToRad(dx * degPerCount);
    this.pitch -= THREE.MathUtils.degToRad(dy * degPerCount);
    this.pitch = THREE.MathUtils.clamp(this.pitch, -Math.PI / 2 + 0.01, Math.PI / 2 - 0.01);
  }

  reset(): void {
    this.yaw = 0;
    this.pitch = 0;
    this.position.set(0, 0, 0);
    this.velocity.set(0, 0, 0);
    this.keys.clear();
  }

  update(dt: number, bounds: { minX: number; maxX: number; minZ: number; maxZ: number }, active: boolean): void {
    const f = new THREE.Vector3(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
    const r = new THREE.Vector3(Math.cos(this.yaw), 0, -Math.sin(this.yaw));
    const wish = new THREE.Vector3();
    if (active) {
      if (this.keys.has("KeyW")) wish.add(f);
      if (this.keys.has("KeyS")) wish.sub(f);
      if (this.keys.has("KeyD")) wish.add(r);
      if (this.keys.has("KeyA")) wish.sub(r);
    }
    const max = this.keys.has("ShiftLeft") || this.keys.has("ShiftRight") ? WALK_SPEED : RUN_SPEED;
    const target = wish.lengthSq() > 0 ? wish.normalize().multiplyScalar(max) : wish;
    const diff = target.clone().sub(this.velocity);
    const rate = target.lengthSq() > 0 && target.dot(this.velocity) >= 0 ? ACCEL : DECEL;
    const step = rate * dt;
    if (diff.length() <= step) this.velocity.copy(target);
    else this.velocity.add(diff.normalize().multiplyScalar(step));
    this.position.addScaledVector(this.velocity, dt);
    this.position.x = THREE.MathUtils.clamp(this.position.x, bounds.minX, bounds.maxX);
    this.position.z = THREE.MathUtils.clamp(this.position.z, bounds.minZ, bounds.maxZ);
    this.camera.position.set(this.position.x, profile.camera.eye_height_m, this.position.z);
    this.camera.rotation.set(this.pitch, this.yaw, 0);
  }

  get speed(): number {
    return Math.hypot(this.velocity.x, this.velocity.z);
  }

  /** 0..1 movement inaccuracy, shown as crosshair spread (like VALORANT's movement error). */
  get movementError(): number {
    return THREE.MathUtils.clamp((this.speed - MOVING_THRESHOLD) / (RUN_SPEED - MOVING_THRESHOLD), 0, 1);
  }

  /** Shot direction with movement inaccuracy applied. */
  shotRay(random: () => number = Math.random): THREE.Ray {
    const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(this.camera.quaternion);
    const spread = THREE.MathUtils.degToRad(this.movementError * MAX_MOVE_SPREAD_DEG);
    if (spread > 0) {
      const ang = random() * Math.PI * 2;
      const mag = Math.sqrt(random()) * spread;
      const up = new THREE.Vector3(0, 1, 0).applyQuaternion(this.camera.quaternion);
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(this.camera.quaternion);
      dir.addScaledVector(right, Math.cos(ang) * Math.tan(mag)).addScaledVector(up, Math.sin(ang) * Math.tan(mag)).normalize();
    }
    return new THREE.Ray(this.camera.position.clone(), dir);
  }
}
