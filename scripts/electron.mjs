// Run the desktop package's Electron binary with arguments (used by record/e2e scripts).
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(root, "apps", "desktop", "package.json"));
const electron = require("electron");
const r = spawnSync(electron, process.argv.slice(2), { stdio: "inherit", cwd: root, env: process.env });
process.exit(r.status ?? 1);
