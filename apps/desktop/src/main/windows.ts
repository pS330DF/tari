/** Window factory: main shell, Training Lab, and the compact companion. */
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { BrowserWindow, screen, shell } from "electron";
import { TRAINING_LAB_TITLE } from "../shared/ipc";
import { log } from "./logger";

const isDev = !!process.env["ELECTRON_RENDERER_URL"];

function rendererUrl(page: "index" | "companion"): { url?: string; file?: string } {
  if (isDev) return { url: `${process.env["ELECTRON_RENDERER_URL"]}/${page === "index" ? "" : `${page}.html`}` };
  return { file: join(__dirname, `../renderer/${page}.html`) };
}

function load(win: BrowserWindow, target: { url?: string; file?: string }): void {
  if (target.url) void win.loadURL(target.url);
  else if (target.file) void win.loadFile(target.file);
}

function hardenNavigation(win: BrowserWindow): void {
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https:\/\//.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    const allowed = isDev ? url.startsWith(process.env["ELECTRON_RENDERER_URL"] ?? "") : url.startsWith("file://");
    if (!allowed) event.preventDefault();
  });
}

const preload = join(__dirname, "../preload/index.js");

export function createMainWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1400,
    height: 880,
    minWidth: 1120,
    minHeight: 700,
    show: false,
    title: "TARI",
    backgroundColor: "#0a0c0f",
    titleBarStyle: "hidden",
    ...(process.platform === "darwin"
      ? { trafficLightPosition: { x: 14, y: 13 } }
      : { titleBarOverlay: { color: "#0a0c0f", symbolColor: "#8b96a3", height: 40 } }),
    webPreferences: { preload, contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
  });
  // Keep TARI's own windows out of screen captures so the analyzer never sees its own output.
  win.setContentProtection(true);
  hardenNavigation(win);
  // In E2E validation runs, show without stealing focus.
  win.once("ready-to-show", () => (process.env["TARI_E2E_VIDEO"] ? win.showInactive() : win.show()));
  load(win, rendererUrl("index"));
  return win;
}

export function createCompanionWindow(): BrowserWindow {
  const area = screen.getPrimaryDisplay().workArea;
  const win = new BrowserWindow({
    width: 340,
    height: 124,
    x: area.x + area.width - 360,
    y: area.y + 24,
    frame: false,
    transparent: true,
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    show: false,
    hasShadow: false,
    title: "TARI Companion",
    webPreferences: { preload, contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  win.setAlwaysOnTop(true, "floating");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setContentProtection(true);
  hardenNavigation(win);
  win.once("ready-to-show", () => win.showInactive());
  load(win, rendererUrl("companion"));
  return win;
}

export function resolveLabTarget(repoRoot: string): { url?: string; file?: string } | null {
  if (process.env["TARI_LAB_URL"]) return { url: process.env["TARI_LAB_URL"] };
  const built = resolve(repoRoot, "apps", "training-lab", "dist", "index.html");
  return existsSync(built) ? { file: built } : null;
}

export function createLabWindow(repoRoot: string): BrowserWindow | null {
  const target = resolveLabTarget(repoRoot);
  if (!target) {
    log("warn", "training lab build not found", { repoRoot });
    return null;
  }
  const win = new BrowserWindow({
    width: 1280,
    height: 720,
    useContentSize: true,
    frame: false, // frameless: captured frames equal the game viewport (no title bar)
    title: TRAINING_LAB_TITLE,
    backgroundColor: "#000000",
    show: false,
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
  });
  win.on("page-title-updated", (e) => e.preventDefault()); // keep the title stable for source matching
  win.once("ready-to-show", () => win.show());
  load(win, target);
  return win;
}
