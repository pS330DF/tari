#!/usr/bin/env bash
# One-time setup (macOS / Linux). Requires Python >= 3.11, Node >= 22 and pnpm 10.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.12 python3.11 python3.13 python3; do
    if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "Python >= 3.11 is required"; exit 1; }
"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
pnpm install
# pnpm may skip Electron's postinstall; make sure the binary is present.
node apps/desktop/node_modules/electron/install.js
.venv/bin/python scripts/gen_fixtures.py
pnpm build:lab
echo "Setup complete. Try: pnpm test  |  pnpm dev"
