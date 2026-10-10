/**
 * Supervises the local Python engine process.
 *
 * - Spawns `python -m tari_engine --port 0` bound to loopback with a random token.
 * - Waits for the `TARI_ENGINE_READY {...}` line on stdout to learn the port.
 * - Restarts on unexpected exit with exponential backoff; after repeated
 *   failures it reports `unavailable` instead of looping forever.
 * The desktop keeps working (capture/preview) while the engine is down; it
 * simply shows that coaching is unavailable.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { EventEmitter } from "node:events";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import type { EngineStatus } from "../shared/ipc";
import { log } from "./logger";

const READY_PREFIX = "TARI_ENGINE_READY ";
const STARTUP_TIMEOUT_MS = 30_000;
const MAX_FAILURES = 6;
const FAILURE_WINDOW_MS = 5 * 60_000;

export interface SupervisorOptions {
  repoRoot: string;
  dataDir: string;
  python?: string;
}

export function resolvePython(repoRoot: string, override?: string): string | null {
  const candidates = [
    override,
    process.env.TARI_PYTHON,
    process.platform === "win32" ? join(repoRoot, ".venv", "Scripts", "python.exe") : join(repoRoot, ".venv", "bin", "python"),
  ].filter((c): c is string => Boolean(c));
  return candidates.find((c) => existsSync(c)) ?? null;
}

export class EngineSupervisor extends EventEmitter {
  private child: ChildProcess | null = null;
  private stopping = false;
  private failures: number[] = [];
  private startupTimer: NodeJS.Timeout | null = null;
  private restartTimer: NodeJS.Timeout | null = null;
  status: EngineStatus = { state: "stopped", port: null, token: null, version: null, restarts: 0, lastError: null, python: null };

  constructor(private readonly opts: SupervisorOptions) {
    super();
  }

  private set(patch: Partial<EngineStatus>): void {
    this.status = { ...this.status, ...patch };
    this.emit("status", this.status);
  }

  start(): void {
    if (this.child) return;
    this.stopping = false;
    const python = resolvePython(this.opts.repoRoot, this.opts.python);
    if (!python) {
      this.set({ state: "unavailable", lastError: "Python environment not found. Run scripts/setup (creates .venv) or set TARI_PYTHON." });
      log("error", "engine python not found", { repoRoot: this.opts.repoRoot });
      return;
    }
    const token = randomBytes(24).toString("hex");
    this.set({ state: this.status.restarts > 0 ? "restarting" : "starting", token, port: null, python });
    const args = ["-m", "tari_engine", "--port", "0", "--data-dir", this.opts.dataDir];
    log("info", "starting engine", { python, args });
    const child = spawn(python, args, {
      cwd: resolve(this.opts.repoRoot),
      env: { ...process.env, TARI_ENGINE_TOKEN: token, PYTHONUNBUFFERED: "1", TARI_KB_DIR: join(this.opts.repoRoot, "packages", "knowledge-base") },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    this.child = child;
    this.startupTimer = setTimeout(() => {
      if (this.status.state !== "ready") {
        log("error", "engine startup timed out");
        this.set({ lastError: "Engine did not become ready in time." });
        child.kill();
      }
    }, STARTUP_TIMEOUT_MS);

    createInterface({ input: child.stdout! }).on("line", (line) => {
      if (line.startsWith(READY_PREFIX)) {
        try {
          const info = JSON.parse(line.slice(READY_PREFIX.length)) as { port: number; version: string };
          if (this.startupTimer) clearTimeout(this.startupTimer);
          this.set({ state: "ready", port: info.port, version: info.version, lastError: null });
          log("info", "engine ready", { port: info.port, version: info.version });
        } catch (err) {
          log("error", "bad engine ready line", { line, error: String(err) });
        }
      }
    });
    createInterface({ input: child.stderr! }).on("line", (line) => {
      // Engine logs are JSON lines; forward them into the desktop log stream.
      log("debug", "engine", { line: line.slice(0, 2000) });
    });
    child.on("error", (err) => {
      log("error", "engine spawn error", { error: String(err) });
      this.set({ lastError: String(err) });
    });
    child.on("exit", (code, signal) => {
      if (this.startupTimer) clearTimeout(this.startupTimer);
      this.child = null;
      if (this.stopping) {
        this.set({ state: "stopped", port: null });
        return;
      }
      const now = Date.now();
      this.failures = [...this.failures.filter((t) => now - t < FAILURE_WINDOW_MS), now];
      const reason = `Engine exited (code ${code ?? "none"}${signal ? `, signal ${signal}` : ""}).`;
      log("warn", "engine exited unexpectedly", { code, signal, failures: this.failures.length });
      if (this.failures.length >= MAX_FAILURES) {
        this.set({ state: "unavailable", port: null, lastError: `${reason} Too many failures; restart it from Settings.` });
        return;
      }
      const delay = Math.min(30_000, 1000 * 2 ** (this.failures.length - 1));
      this.set({ state: "restarting", port: null, lastError: `${reason} Restarting in ${Math.round(delay / 1000)} s.`, restarts: this.status.restarts + 1 });
      this.restartTimer = setTimeout(() => this.start(), delay);
    });
  }

  async stop(): Promise<void> {
    this.stopping = true;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    const child = this.child;
    if (!child) return;
    await new Promise<void>((done) => {
      const kill = setTimeout(() => child.kill("SIGKILL"), 3000);
      child.once("exit", () => {
        clearTimeout(kill);
        done();
      });
      child.kill();
    });
  }

  async restart(): Promise<void> {
    await this.stop();
    this.failures = [];
    this.status = { ...this.status, restarts: this.status.restarts + 1 };
    this.start();
  }
}
