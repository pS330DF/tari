/** Lab menus (DOM). Preferences persist in localStorage as a convenience only. */
import type { DrillKind, DrillResult } from "./drills";
import type { TargetColor } from "./profile";

export interface LabPrefs {
  drill: DrillKind;
  duration: number;
  sensitivity: number;
  crosshair: string;
  color: TargetColor;
}

const DEFAULTS: LabPrefs = { drill: "angle_hold", duration: 90, sensitivity: 0.35, crosshair: "#00f0ff", color: "red" };
const KEY = "tari.lab.prefs.v1";

export function loadPrefs(): LabPrefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    const p = JSON.parse(raw) as Partial<LabPrefs>;
    return {
      drill: p.drill === "flick" ? "flick" : "angle_hold",
      duration: [60, 90, 120].includes(p.duration ?? 0) ? p.duration! : DEFAULTS.duration,
      sensitivity: typeof p.sensitivity === "number" && p.sensitivity > 0.05 && p.sensitivity < 5 ? p.sensitivity : DEFAULTS.sensitivity,
      crosshair: /^#[0-9a-f]{6}$/i.test(p.crosshair ?? "") ? p.crosshair! : DEFAULTS.crosshair,
      color: p.color === "yellow" || p.color === "purple" ? p.color : "red",
    };
  } catch {
    return { ...DEFAULTS };
  }
}

export function savePrefs(p: LabPrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* storage unavailable: preferences simply do not persist */
  }
}

const CROSSHAIRS = ["#00f0ff", "#00ff6a", "#ffff00", "#ff00ff"];
const COLORS: { value: TargetColor; label: string; hex: string }[] = [
  { value: "red", label: "Red", hex: "#ff3045" },
  { value: "yellow", label: "Yellow", hex: "#f5e63a" },
  { value: "purple", label: "Purple", hex: "#c042ff" },
];

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export interface MenuHandlers {
  onStart(p: LabPrefs): void;
  onResume(): void;
  onEnd(): void;
  onQuit(): void;
  onPrefs(p: LabPrefs): void;
}

export class LabUi {
  private root: HTMLElement;
  private prefs: LabPrefs;

  constructor(container: HTMLElement, private h: MenuHandlers) {
    this.root = container;
    this.prefs = loadPrefs();
  }

  get current(): LabPrefs {
    return this.prefs;
  }

  hide(): void {
    this.root.replaceChildren();
    this.root.classList.remove("open");
  }

  private shell(title: string, subtitle: string): HTMLElement {
    this.root.replaceChildren();
    this.root.classList.add("open");
    const card = el("div", "card");
    const bar = el("div", "bar");
    const mark = el("div", "mark");
    mark.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 2.8 21.2 12 12 21.2 2.8 12Z" stroke="#2dd4bf" stroke-width="1.6" stroke-linejoin="round"/><path d="M7.2 12h9.6" stroke="#8b96a3" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="12" r="2.1" fill="#5eead4"/></svg>';
    bar.append(mark, el("span", "brand", "TARI TRAINING LAB"));
    const close = el("button", "close", "×");
    close.title = "Close the Training Lab";
    close.onclick = () => this.h.onQuit();
    bar.append(close);
    card.append(bar, el("h1", "", title), el("p", "sub", subtitle));
    this.root.append(card);
    return card;
  }

  private option<T extends string | number>(label: string, value: T, options: { value: T; label: string; swatch?: string }[], set: (v: T) => void): HTMLElement {
    const row = el("div", "row");
    row.append(el("span", "label", label));
    const group = el("div", "seg");
    for (const o of options) {
      const b = el("button", o.value === value ? "on" : "");
      if (o.swatch) {
        const sw = el("span", "swatch");
        sw.style.background = o.swatch;
        b.append(sw);
      }
      b.append(document.createTextNode(o.label));
      b.onclick = () => {
        set(o.value);
        this.h.onPrefs(this.prefs);
        savePrefs(this.prefs);
        this.showMenu();
      };
      group.append(b);
    }
    row.append(group);
    return row;
  }

  showMenu(): void {
    const p = this.prefs;
    const card = this.shell("Choose a drill", "TARI watches this window live and coaches your placement and aim. Press Start, then click to lock the mouse.");
    const drills = el("div", "drills");
    const items: { kind: "angle_hold" | "flick"; name: string; desc: string }[] = [
      { kind: "angle_hold", name: "Angle hold", desc: "Bots peek from cover edges. Hold head height at the edge and react." },
      { kind: "flick", name: "Flick", desc: "Bots appear anywhere ahead. Acquire the head quickly and cleanly." },
    ];
    for (const d of items) {
      const b = el("button", `drill ${p.drill === d.kind ? "on" : ""}`);
      b.append(el("strong", "", d.name), el("span", "", d.desc));
      b.onclick = () => {
        p.drill = d.kind;
        savePrefs(p);
        this.showMenu();
      };
      drills.append(b);
    }
    card.append(drills);
    card.append(this.option("Duration", p.duration, [60, 90, 120].map((v) => ({ value: v, label: `${v}s` })), (v) => (p.duration = v)));
    card.append(this.option("Crosshair", p.crosshair, CROSSHAIRS.map((c) => ({ value: c, label: "", swatch: c })), (v) => (p.crosshair = v)));
    card.append(this.option("Enemy highlight", p.color, COLORS.map((c) => ({ value: c.value, label: c.label, swatch: c.hex })), (v) => (p.color = v)));
    const sensRow = el("div", "row");
    sensRow.append(el("span", "label", "Sensitivity"));
    const sens = el("input", "num");
    sens.type = "number";
    sens.min = "0.05";
    sens.max = "5";
    sens.step = "0.01";
    sens.value = String(p.sensitivity);
    sens.onchange = () => {
      const v = Number(sens.value);
      if (v > 0.05 && v < 5) {
        p.sensitivity = v;
        savePrefs(p);
        this.h.onPrefs(p);
      }
    };
    const hint = el("span", "hint", "VALORANT scale");
    sensRow.append(sens, hint);
    card.append(sensRow);
    const start = el("button", "primary", "Start drill");
    start.onclick = () => this.h.onStart(p);
    card.append(el("p", "keys", "Esc pause · R reload · Shift walk · WASD move"), start);
  }

  showCountdown(n: number): void {
    this.root.replaceChildren(el("div", "countdown", String(Math.max(1, Math.ceil(n)))));
    this.root.classList.add("open", "bare");
  }

  clearCountdown(): void {
    this.root.classList.remove("bare");
    this.hide();
  }

  showPause(): void {
    const card = this.shell("Paused", "Click Resume to lock the mouse again.");
    const resume = el("button", "primary", "Resume");
    resume.onclick = () => this.h.onResume();
    const end = el("button", "secondary", "End drill");
    end.onclick = () => this.h.onEnd();
    const actions = el("div", "actions");
    actions.append(end, resume);
    card.append(actions);
  }

  showResults(r: DrillResult): void {
    const card = this.shell("Drill complete", r.kind === "angle_hold" ? "Angle hold" : "Flick");
    const grid = el("div", "stats");
    const stat = (k: string, v: string) => {
      const d = el("div", "stat");
      d.append(el("span", "k", k), el("span", "v", v));
      grid.append(d);
    };
    stat("Kills", String(r.kills));
    stat("Headshot kills", String(r.headshots));
    stat("Shots", String(r.shots));
    stat("Targets escaped", String(r.escaped));
    card.append(grid, el("p", "sub", "These are the Lab's own exact counts. TARI's measurements and coaching are in the TARI app."));
    const again = el("button", "primary", "Run again");
    again.onclick = () => this.h.onStart(this.prefs);
    const menu = el("button", "secondary", "Menu");
    menu.onclick = () => this.showMenu();
    const actions = el("div", "actions");
    actions.append(menu, again);
    card.append(actions);
  }
}
