/** TARI desktop main process. */
import { readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { app, BrowserWindow, ipcMain, protocol, session } from "electron";
import { z } from "zod";
import type { CompanionSnapshot, IpcContract, IpcEvents } from "../shared/ipc";
import type { SettingsPatch } from "../shared/settings";
import { installDisplayMediaHandler, listSources, selectSource } from "./capture";
import { EngineSupervisor } from "./engine-supervisor";
import { initLogger, log } from "./logger";
import { systemMetrics } from "./metrics";
import { SettingsStore } from "./settings-store";
import { createCompanionWindow, createLabWindow, createMainWindow } from "./windows";

const isDev = !!process.env["ELECTRON_RENDERER_URL"];
const repoRoot = process.env["TARI_REPO_ROOT"] ?? resolve(app.getAppPath(), "..", "..");

// End-to-end validation mode: a recorded video is served to the renderer and fed through
// the regular video-file capture path; a JSON report is written when the run completes.
const e2eVideo = process.env["TARI_E2E_VIDEO"] ? resolve(process.env["TARI_E2E_VIDEO"]) : null;
const e2eReport = process.env["TARI_E2E_REPORT"] ? resolve(process.env["TARI_E2E_REPORT"]) : null;
const e2eSeconds = Number(process.env["TARI_E2E_SECONDS"] ?? "20");
if (e2eVideo) {
  protocol.registerSchemesAsPrivileged([
    { scheme: "tari-e2e", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } },
  ]);
}

let mainWindow: BrowserWindow | null = null;
let companion: BrowserWindow | null = null;
let lab: BrowserWindow | null = null;
let supervisor: EngineSupervisor;
let settings: SettingsStore;

function broadcast<E extends keyof IpcEvents>(event: E, payload: IpcEvents[E]): void {
  for (const w of BrowserWindow.getAllWindows()) if (!w.isDestroyed()) w.webContents.send(event, payload);
}

function handle<C extends keyof IpcContract>(
  channel: C,
  fn: (req: IpcContract[C]["req"]) => Promise<IpcContract[C]["res"]> | IpcContract[C]["res"],
): void {
  ipcMain.handle(channel, async (event, req) => {
    // Only TARI's own windows may call into main.
    const url = event.senderFrame?.url ?? "";
    const trusted = isDev ? url.startsWith(process.env["ELECTRON_RENDERER_URL"] ?? "\u0000") : url.startsWith("file://");
    if (!trusted) throw new Error(`untrusted IPC sender: ${url}`);
    return fn(req as IpcContract[C]["req"]);
  });
}

function registerIpc(): void {
  handle("settings:get", () => settings.get());
  handle("settings:set", async (patch) => {
    const next = await settings.update(patch as SettingsPatch);
    broadcast("settings:changed", next);
    return next;
  });
  handle("capture:list-sources", (req) => listSources(Boolean(z.object({ thumbnails: z.boolean() }).parse(req).thumbnails)));
  handle("capture:select", (req) => selectSource(z.object({ id: z.string().min(1).max(256) }).parse(req).id));
  handle("engine:status", () => supervisor.status);
  handle("engine:restart", async () => {
    await supervisor.restart();
    return supervisor.status;
  });
  handle("lab:open", () => {
    if (lab && !lab.isDestroyed()) {
      lab.focus();
      return { ok: true };
    }
    lab = createLabWindow(repoRoot);
    if (!lab) return { ok: false, reason: "Training Lab is not built. Run `pnpm build:lab`." };
    lab.on("closed", () => (lab = null));
    return { ok: true };
  });
  handle("companion:set-visible", (req) => {
    const visible = z.object({ visible: z.boolean() }).parse(req).visible;
    if (visible && (!companion || companion.isDestroyed())) {
      companion = createCompanionWindow();
      companion.on("closed", () => {
        companion = null;
        broadcast("companion:visibility", { visible: false });
      });
    } else if (!visible && companion && !companion.isDestroyed()) {
      companion.close();
    }
    broadcast("companion:visibility", { visible });
    return { visible };
  });
  handle("system:metrics", () => systemMetrics());
  handle("app:info", () => ({
    version: app.getVersion(),
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    platform: `${process.platform}-${process.arch}`,
    dataDir: app.getPath("userData"),
    dev: isDev,
  }));
  handle("e2e:config", () => (e2eVideo ? { videoUrl: "tari-e2e://media/recording", seconds: e2eSeconds } : null));
  handle("e2e:report", async (report) => {
    if (!e2eReport) return { ok: false };
    await writeFile(e2eReport, JSON.stringify(report, null, 2));
    log("info", "e2e report written", { path: e2eReport });
    setTimeout(() => app.quit(), 300);
    return { ok: true };
  });
  handle("e2e:screenshot", async (req) => {
    const dir = process.env["TARI_E2E_SCREENSHOT_DIR"];
    const { name, window: which } = z
      .object({ name: z.string().regex(/^[a-z0-9-]{1,40}$/), window: z.enum(["main", "companion"]).optional() })
      .parse(req);
    const target = which === "companion" ? companion : mainWindow;
    if (!e2eVideo || !dir || !target || target.isDestroyed()) return { ok: false };
    const img = await target.webContents.capturePage();
    await writeFile(join(dir, `${name}.png`), img.toPNG());
    return { ok: true };
  });
  ipcMain.on("companion:publish", (_e, snapshot: CompanionSnapshot) => {
    if (companion && !companion.isDestroyed()) companion.webContents.send("companion:update", snapshot);
  });
}

function hardenSession(): void {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    // Pointer lock + fullscreen for the Training Lab. Microphone stays denied until the
    // user enables it in Settings (speech input is not implemented in this build).
    const allowed = permission === "pointerLock" || permission === "fullscreen" ||
      (permission === "media" && settings.get().privacy.microphoneEnabled);
    callback(allowed);
  });
  if (isDev) {
    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          "Content-Security-Policy": [
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
              "img-src 'self' data: blob:; media-src 'self' blob: mediastream:; font-src 'self' data:; " +
              "connect-src 'self' ws://localhost:* http://localhost:* ws://127.0.0.1:* http://127.0.0.1:*; worker-src 'self' blob:",
          ],
        },
      });
    });
  }
}

app.whenReady().then(async () => {
  const userData = app.getPath("userData");
  await initLogger(join(userData, "logs"));
  settings = new SettingsStore(userData);
  await settings.load();
  hardenSession();
  installDisplayMediaHandler();
  if (e2eVideo) {
    const video = e2eVideo;
    protocol.handle("tari-e2e", async () => {
      const data = await readFile(video);
      return new Response(data, { headers: { "content-type": video.endsWith(".mp4") ? "video/mp4" : "video/webm", "access-control-allow-origin": "*" } });
    });
  }
  supervisor = new EngineSupervisor({ repoRoot, dataDir: join(userData, "engine") });
  supervisor.on("status", (s) => broadcast("engine:status-changed", s));
  registerIpc();
  supervisor.start();
  mainWindow = createMainWindow();
  mainWindow.on("closed", () => {
    mainWindow = null;
    if (companion && !companion.isDestroyed()) companion.close();
  });
  if (settings.recovered) {
    mainWindow.webContents.once("did-finish-load", () =>
      broadcast("notice", { level: "warning", message: `Settings were invalid and have been reset. Backup: ${settings.recovered}` }),
    );
  }
  log("info", "desktop ready", { repoRoot, dev: isDev });
});

app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => {
  void supervisor?.stop();
});
