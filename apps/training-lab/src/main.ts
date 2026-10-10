/** TARI Training Lab entry: render loop, input, and drill orchestration. */
import * as THREE from "three";
import { AutoPilot, parseAutotest, seeded, type FrameTruth } from "./autotest";
import { Drill } from "./drills";
import { Hud } from "./hud";
import { Player } from "./player";
import { DRILL_CODES } from "./profile";
import { Range } from "./scene";
import { LabUi, type LabPrefs } from "./ui";
import "./style.css";

const sceneCanvas = document.getElementById("scene") as HTMLCanvasElement;
const hudCanvas = document.getElementById("hud") as HTMLCanvasElement;
const renderer = new THREE.WebGLRenderer({ canvas: sceneCanvas, antialias: true, powerPreference: "high-performance" });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NoToneMapping;
const range = new Range();
const player = new Player();
const hud = new Hud(hudCanvas);
const banner = document.createElement("div");
banner.id = "banner";
document.body.append(banner);

let drill: Drill | null = null;
let paused = false;
let prefs: LabPrefs;

const ui = new LabUi(document.getElementById("ui")!, {
  onStart: (p) => startDrill(p),
  onResume: () => lock(),
  onEnd: () => finishDrill(),
  onQuit: () => window.close(),
  onPrefs: (p) => applyPrefs(p),
});
prefs = ui.current;
applyPrefs(prefs);
ui.showMenu();

function applyPrefs(p: LabPrefs): void {
  prefs = p;
  player.sensitivity = p.sensitivity;
  drill?.setColor(p.color);
}

function resize(): void {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(dpr);
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  player.resize(window.innerWidth, window.innerHeight);
  hud.resize();
}
window.addEventListener("resize", resize);
resize();

function lock(): void {
  const req = sceneCanvas.requestPointerLock as unknown as (o?: { unadjustedMovement?: boolean }) => Promise<void> | void;
  try {
    const r = req.call(sceneCanvas, { unadjustedMovement: true });
    if (r && typeof (r as Promise<void>).catch === "function") (r as Promise<void>).catch(() => sceneCanvas.requestPointerLock());
  } catch {
    sceneCanvas.requestPointerLock();
  }
}

function startDrill(p: LabPrefs): void {
  applyPrefs(p);
  drill?.dispose();
  player.reset();
  drill = new Drill(p.drill, p.duration, p.color, range);
  paused = false;
  ui.hide();
  lock();
}

function finishDrill(): void {
  if (!drill) return;
  const r = drill.result;
  drill.dispose();
  drill = null;
  paused = false;
  if (document.pointerLockElement) document.exitPointerLock();
  ui.showResults(r);
}

document.addEventListener("pointerlockchange", () => {
  const locked = document.pointerLockElement === sceneCanvas;
  if (!locked && drill && drill.state !== "done") {
    paused = true;
    ui.showPause();
  } else if (locked) {
    paused = false;
    if (drill?.state === "running") ui.hide();
  }
});

document.addEventListener("mousemove", (e) => {
  if (document.pointerLockElement === sceneCanvas && !paused) player.look(e.movementX, e.movementY);
});
document.addEventListener("mousedown", (e) => {
  if (e.button !== 0 || document.pointerLockElement !== sceneCanvas || !drill || paused) return;
  drill.fire(player.shotRay());
});
window.addEventListener("keydown", (e) => {
  if (e.code === "KeyR" && drill && !paused) drill.reload();
});

function step(dt: number): void {
  const running = drill !== null && !paused;
  player.update(dt, range.bounds, running && drill?.state === "running");
  if (drill && !paused) {
    drill.update(dt, player);
    if (!autotest) {
      if (drill.state === "countdown") ui.showCountdown(drill.countdown);
      else if (drill.state === "running" && document.getElementById("ui")!.classList.contains("bare")) ui.clearCountdown();
    }
    if (drill.state === "done") {
      if (autotest) autoDone = true;
      else finishDrill();
    }
  }
}

function render(): void {
  renderer.render(range.scene, player.camera);
  banner.textContent = drill ? `${drill.kind === "angle_hold" ? "ANGLE HOLD" : "FLICK"} · ${drill.result.kills} kills` : "";
  hud.draw({
    drill: drill ? DRILL_CODES[drill.kind] ?? null : null,
    ammo: drill ? drill.ammo : null,
    timer: drill ? Math.ceil(drill.timeLeft) : null,
    crosshairColor: prefs.crosshair,
    movementError: player.movementError,
    showCluster: true,
  });
}

// -- Autotest (validation harness only; see autotest.ts) ---------------------
const autotest = parseAutotest(window.location.search);
let autoDone = false;

if (autotest) {
  ui.hide();
  const rng = seeded(autotest.seed);
  prefs = { ...prefs, drill: autotest.drill, duration: autotest.durationS };
  drill = new Drill(autotest.drill, autotest.durationS, prefs.color, range, rng);
  drill.state = "running";
  const pilot = new AutoPilot(autotest, player, range);
  const dt = 1 / autotest.fps;
  let frame = 0;
  const nextPaint = () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
  (window as unknown as { __tariLab: unknown }).__tariLab = {
    config: autotest,
    get done() {
      return autoDone;
    },
    async advance(): Promise<FrameTruth> {
      if (drill && !autoDone) {
        if (pilot.update(dt, drill)) drill.fire(player.shotRay(() => 0));
        step(dt);
      }
      render();
      const truth = pilot.truth(frame, frame * dt * 1000, drill!);
      frame++;
      await nextPaint();
      return truth;
    },
  };
  render();
} else {
  let last = performance.now();
  const loop = (now: number): void => {
    requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    step(dt);
    render();
  };
  requestAnimationFrame(loop);
}
