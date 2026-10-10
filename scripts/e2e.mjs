// End-to-end validation of the desktop app on a recorded real-Lab video.
// Launches the built app in E2E mode with an isolated user-data directory, waits for the
// report, prints the key results and exits non-zero if the run did not work end to end.
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const video = process.argv[2] ?? join(root, "datasets", "lab", "angle_hold_low", "recording.webm");
const seconds = process.argv[3] ?? "18";
const work = mkdtempSync(join(tmpdir(), "tari-e2e-"));
const report = join(work, "report.json");
const electron = createRequire(join(root, "apps", "desktop", "package.json"))("electron");
const r = spawnSync(electron, [join(root, "apps", "desktop"), `--user-data-dir=${join(work, "userdata")}`], {
  cwd: root,
  stdio: ["ignore", "ignore", "inherit"],
  env: { ...process.env, TARI_E2E_VIDEO: video, TARI_E2E_REPORT: report, TARI_E2E_SECONDS: seconds, TARI_E2E_SCREENSHOT_DIR: work },
  timeout: (Number(seconds) + 90) * 1000,
});
let data;
try {
  data = JSON.parse(readFileSync(report, "utf8"));
} catch {
  console.error(`No report was written (exit ${r.status}). Logs: ${join(work, "userdata", "logs")}`);
  process.exit(1);
}
const c = data.client ?? {};
const summary = {
  ok: data.ok,
  error: data.error ?? null,
  resultsReceived: data.results,
  framesPresented: data.framesPresented,
  analyzedFps: c.resultFps,
  captureFps: c.captureFps,
  frameToResultMs: data.endToEndMs,
  frameToScreenMs: data.visualFeedbackMs,
  events: data.events,
  recommendations: data.recommendations,
  persisted: data.persisted ? { endReason: data.persisted.end_reason, environment: data.persisted.environment, events: data.persisted.event_counts } : null,
  screenshots: work,
};
console.log(JSON.stringify(summary, null, 2));
const pass = data.ok && data.results > 0 && (data.events?.target_exposed ?? 0) > 0 && data.persisted?.end_reason === "user_stopped";
process.exit(pass ? 0 : 1);
