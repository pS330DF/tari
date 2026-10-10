/** Structured JSON-lines logging for the main process. */
import { appendFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

type Level = "debug" | "info" | "warn" | "error";

let logFile: string | null = null;
let queue: Promise<void> = Promise.resolve();

export async function initLogger(dir: string): Promise<void> {
  await mkdir(dir, { recursive: true });
  logFile = join(dir, "desktop.jsonl");
}

export function log(level: Level, msg: string, fields: Record<string, unknown> = {}): void {
  const line = JSON.stringify({ ts: Date.now() / 1000, level, logger: "tari.desktop", msg, ...fields });
  if (level === "error" || level === "warn") console.error(line);
  else console.log(line);
  if (logFile) {
    const file = logFile;
    queue = queue.then(() => appendFile(file, line + "\n").catch(() => undefined));
  }
}
