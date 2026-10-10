# TARI — Tactical Augmented Reasoning Intelligence

A real-time AI coaching companion for FPS aim training. TARI watches a live
gameplay stream, measures what you do from the pixels (crosshair placement,
target acquisition, flicks, shots), and coaches you through spatial overlays,
a companion panel, and voice. Everything runs locally.

Live coaching runs in the **TARI Training Lab**, a controlled aim-training
environment that ships with TARI. VALORANT match integration is disabled pending
Riot authorization (see [docs/compliance.md](docs/compliance.md)).

> Status: first end-to-end vertical slice. Aim coaching is live; the other six
> coaching domains are designed into the architecture but not implemented yet.
> See [docs/status.md](docs/status.md) for exactly what works and what was verified.

## What works today

- **Desktop app** (Electron + React): pick a window/screen or a video file, start a
  session, see each analyzed frame with its overlays, TARI's feedback, live
  measurements, a timeline, telemetry, session history, progress, and settings
  (EN/한국어, intensity, strictness, voice, overlay density, detection colors).
- **Training Lab** (Three.js): angle-hold and flick drills with cover, peeking bots,
  movement error, ammo/timer HUD, and an on-screen fiducial that lets TARI verify
  the environment.
- **Engine** (Python, FastAPI, OpenCV): environment verification, HUD reading,
  crosshair detection, target and head localization, view-motion estimation,
  target tracking, exposure/acquisition/flick/shot measurement, deterministic aim
  rules with evidence, priority/confidence filtering, overlay and voice
  instructions, SQLite persistence, longitudinal profile, telemetry.
- **Native capture service** (Rust, Windows.Graphics.Capture): compiles for
  Windows; protocol verified against the engine; not yet run on Windows.

Measured on an Apple M3 with real Training Lab recordings: environment, HUD and
crosshair detection 100%; scripted 1.4° low placement measured as 1.407°;
13/13 scripted overshoots detected with zero false positives on 30 clean flicks;
engine ~5.5 ms per frame; frame → feedback on screen p95 ≈ 45 ms in the desktop app.
Details: [docs/metrics.md](docs/metrics.md).

## Architecture

```
 capture source ──▶ capture worker ──FramePacket (binary WS, loopback)──▶ engine (Python)
 desktopCapturer      bounded scheduler                                    perception ─▶ temporal state
 video file           540p frame + 384px crop                              ─▶ events ─▶ aim coach ─▶ filter
 native WGC (Rust)                                                          ─▶ overlays + voice + SQLite
        ▲                                                                           │
        └──── viewer (frame + overlay, TTL-gated) ◀── FrameResult (JSON WS) ◀───────┘
```

Decision record: [docs/adr/0001-architecture.md](docs/adr/0001-architecture.md) ·
Wire protocol: [docs/protocol.md](docs/protocol.md).

## Requirements

- Windows 11 (target) or macOS (development), Node ≥ 22, pnpm 10, Python ≥ 3.11
- Optional: Rust (for `services/capture`), an NVIDIA GPU + `pynvml` for GPU telemetry
- macOS: grant Screen Recording to the app (or to Electron in development) to capture windows

## Setup

```bash
# macOS / Linux
bash scripts/setup.sh
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This creates `.venv`, installs the engine (`pip install -e ".[dev]"`), installs the
JS workspace, downloads Electron, writes the golden test fixture, and builds the Lab.

## Run

```bash
pnpm dev          # Training Lab build + desktop app with hot reload (engine starts automatically)
pnpm start        # production build of everything, then launch
```

In the app: **Open Training Lab** → choose *TARI Training Lab* as the source →
**Start session** → click into the Lab window to play. Without screen-capture
permission you can still analyze a recording via **Video file**
(e.g. `datasets/lab/angle_hold_low/recording.webm`).

Run the engine alone (for the Rust client or API exploration):

```bash
pnpm engine       # ws://127.0.0.1:8765/v1/stream?token=dev
```

## Test, benchmark, validate

| Command | What it does |
| --- | --- |
| `pnpm test` | Python suite (unit, integration, real-Lab video regression) + TypeScript suites |
| `pnpm test:rust` | Rust packet/image tests (golden fixture shared with Python/TS) |
| `pnpm check:capture-windows` | type-checks the WGC capture service for `x86_64-pc-windows-msvc` |
| `pnpm typecheck` | TypeScript across all packages |
| `pnpm bench` | engine per-stage p50/p95/p99 and WebSocket stream/overload benchmarks → `tests/performance/results/` |
| `pnpm e2e` | builds and runs the desktop app on a real-Lab recording through the full pipeline; prints latency, events, persistence |
| `pnpm record:lab -- --preset angle_hold_low --frames 600 --out /tmp/lab` | records the real Lab offscreen with per-frame ground truth |
| `pnpm eval:lab -- /tmp/lab` | scores the engine against that ground truth |

## Repository layout

```
apps/desktop          Electron main/preload/renderer, capture worker, voice controller
apps/training-lab     Three.js Training Lab (drills, HUD, fiducial, autotest mode)
services/perception   tari_perception: environment, HUD, crosshair, targets, view motion, ONNX adapter
services/state-engine tari_state: tracking, temporal measurements, events, integration policy
services/coaching     tari_coaching: aim coach, filter, overlay + voice builders, EN/KO phrasing
services/engine       tari_engine: FastAPI app, stream sessions, scheduler, SQLite store, telemetry
services/capture      tari-capture (Rust): Windows.Graphics.Capture → FramePackets
services/voice        notes on voice (output lives in the desktop renderer)
packages/event-schema tari_schema (Pydantic, source of truth), JSON Schema, golden fixture
packages/shared-types generated TS types + FramePacket codec
packages/overlay-components  canvas overlay renderer with staleness gating
packages/telemetry    rolling percentiles and rates (TS)
packages/knowledge-base  versioned environment profile shared by the Lab and perception
datasets              real-Lab regression recordings + synthetic scene generator
models                ONNX model registry (empty: no model is bundled)
tests                 unit, integration, performance, evaluation
docs                  ADR, protocol, metrics, compliance, status
```

## Privacy

Frames are analyzed on your machine and never uploaded; only derived
measurements are stored locally. The microphone is not used in this build.
