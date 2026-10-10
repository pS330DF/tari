// Run the repo's virtualenv Python on any OS: `node scripts/py.mjs -m pytest -q`
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const python = process.platform === "win32" ? join(root, ".venv", "Scripts", "python.exe") : join(root, ".venv", "bin", "python");
if (!existsSync(python)) {
  console.error(`Python virtualenv not found at ${python}. Run scripts/setup.sh (or scripts\\setup.ps1 on Windows).`);
  process.exit(1);
}
const r = spawnSync(python, process.argv.slice(2), { stdio: "inherit", cwd: root });
process.exit(r.status ?? 1);
