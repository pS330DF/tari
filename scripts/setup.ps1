# One-time setup (Windows 11). Requires Python >= 3.11 (py launcher), Node >= 22 and pnpm 10.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { py -3.11 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -e ".[dev]"
pnpm install
node apps/desktop/node_modules/electron/install.js
.\.venv\Scripts\python.exe scripts\gen_fixtures.py
pnpm build:lab
Write-Host "Setup complete. Try: pnpm test  |  pnpm dev"
