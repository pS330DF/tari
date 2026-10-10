# ADR 0001 — TARI runtime architecture

- Status: accepted (first vertical slice implemented)
- Date: 2026-10-10

## Context

TARI must perceive gameplay continuously, keep a temporal belief about what is
happening, evaluate coaching rules within tens of milliseconds, and present
feedback (overlay + voice) that is never stale. It must run locally, survive the
failure of optional parts, and respect Riot's third-party restrictions: no game
memory, no injection, no input automation, and no unapproved live assistance in
matches. A controlled environment (the TARI Training Lab) is where live spatial
and tactical coaching is developed and validated.

## Decisions

### 1. Processes and component boundaries

| Process | Technology | Owns |
| --- | --- | --- |
| **Desktop main** | Electron (Node) | windows, settings (validated JSON), capture-source selection, engine supervision, IPC policy, system metrics |
| **Desktop renderer** | React + Zustand | UI (Live / Sessions / Progress / Settings), viewer, voice output, companion publishing |
| **Capture worker** | Dedicated Web Worker | frame pump: VideoFrame → scheduler → regions → FramePacket → engine socket; pairs results with the exact frame bitmap |
| **Engine** | Python 3.11+, FastAPI/uvicorn, OpenCV, NumPy | perception, temporal state, event generation, coaching, SQLite persistence, telemetry |
| **Training Lab** | Vite + Three.js page in a frameless Electron window | the controlled environment (drills, HUD, fiducial) |
| **Native capture** (optional) | Rust, `windows` crate (WGC) | Windows.Graphics.Capture → FramePackets straight to the engine |

The engine's internal packages keep the logical boundaries of the original
design (`tari_perception` → `tari_state` → `tari_coaching`, with `tari_schema`
as the contract) but run **in one process**: a frame crosses no extra IPC hop
between perception and coaching, and the failure domain stays simple. Each
package is importable and tested on its own, so it can be split out later.

### 2. Data flow

```
capture source ─▶ capture worker ──FramePacket (binary WS)──▶ engine
 (desktopCapturer /     │  scheduler: ≤N in flight,            │ 1-slot latest-wins buffer
  video file /          │  rate cap, expiry                    │ stale/out-of-order drop
  native WGC)           │                                      ▼
                        │                    perception (env → HUD → crosshair → targets → ego-motion)
                        │                    temporal state (tracks, exposures, acquisitions, flicks, shots)
                        │                    coaching (aim coach → priority/confidence filter → overlay + voice)
                        │                                      │
 viewer ◀─ bitmap+result┘◀──────── FrameResult (JSON WS) ──────┤──▶ SQLite (events, recs, metrics, perf)
 voice controller ◀── VoiceInstructions                         └──▶ telemetry (1 Hz)
```

Every result carries the **source frame id and acquisition timestamp**. The
viewer draws an overlay together with the bitmap of the frame it was computed
from ("analyzed frames" mode), or over live video only while the overlay is
younger than its TTL ("live + overlay" mode).

### 3. IPC

- **Renderer ↔ main:** typed contract (`apps/desktop/src/shared/ipc.ts`),
  allow-listed channels in the preload, sender-origin check and `zod`
  validation in main, `contextIsolation` + `sandbox`.
- **Renderer worker ↔ engine:** loopback WebSocket `ws://127.0.0.1:<port>/v1/stream?token=…`.
  Binary messages are FramePackets; text messages are versioned JSON
  (`docs/protocol.md`). `permessage-deflate` is disabled (frames are already
  dense; compression would only add latency).
- **Main ↔ engine:** the supervisor spawns `python -m tari_engine --port 0`
  with a random token in the environment and learns the port from a
  `TARI_ENGINE_READY {...}` line on stdout. The engine binds loopback only.
- **REST** (sessions, profile) uses the same token in `x-tari-token`.
- **Schema contract:** Pydantic models (`tari_schema`) are the source of truth →
  JSON Schema → generated TypeScript (`pnpm gen:schema`). A golden binary
  fixture is decoded by the Python, TypeScript and Rust test suites.

### 4. Scheduling and freshness

Latency is bounded instead of throughput being maximized:
- capture worker: at most `maxInFlight` (default 1) frames awaiting results;
  frames beyond the analysis rate or arriving while busy are closed at once;
  unanswered frames expire after 1 s;
- engine: one-slot latest-wins buffer (a newer frame supersedes a waiting one,
  reported as `frame_dropped: superseded`); frames older than 250 ms or older
  than the last processed frame are dropped (`stale`, `out_of_order`);
- all temporal measurements use **acquisition** timestamps, so processing
  delay never distorts measured durations (only their resolution).

### 5. Model deployment

The shipped perception is deterministic OpenCV on the CPU (color segmentation,
silhouette geometry, phase correlation, ArUco, seven-segment HUD decoding).
Neural detectors plug in through `OnnxTargetDetector`: models are listed in
`models/registry.json` with version, SHA-256, input size and output format;
anything that is missing, tampered, of an unsupported format or requires a
newer engine is refused with a reason. Execution providers are chosen
GPU-first (CUDA → DirectML → CoreML) with CPU fallback. Model outputs are
validated (shape, finiteness, ranges); invalid output fails the module instead
of producing detections. No model is bundled yet.

The LLM is not used for vision. It is reserved for explanations and is not
integrated in this slice.

### 6. Integration policy

Live analysis is enabled only when the Training Lab's ArUco fiducial is
**observed** in the frame (with a 1.5 s grace). Otherwise the engine runs only
the environment check: no targets, no HUD, no coaching, no overlays. A VALORANT
capture source triggers an explicit notice. The `AuthorizationVerifier` hook
exists for a future Riot-approved integration; the shipped verifier always
answers "not authorized". See `docs/compliance.md`.

### 7. Failure recovery

| Failure | Behaviour |
| --- | --- |
| engine crash / exit | supervisor restarts with exponential backoff (1 → 30 s); after 6 failures in 5 min it reports `unavailable`; capture and UI keep running; nothing is fabricated while it is down |
| socket loss | worker reconnects with backoff; engine finalizes the session (`client_disconnected`); a new session starts on reconnect |
| perception module exception | that module reports `failed` with the error; others still run; no back-filled values; state fields become `unknown`/`stale` and a notice is emitted once |
| crosshair / HUD not visible | crosshair becomes an *estimate* (frame center) with low confidence → aim measurements pause, notice tells the user what to fix |
| invalid frame packet | rejected with a coded reason (`frame_dropped: invalid`) |
| corrupt SQLite file | integrity check on open; the file is moved aside (never deleted), a new DB is created, the user is told where the old file is |
| persistence write failure | logged, flagged as degraded in telemetry; the live session continues |
| corrupt settings file | backed up, defaults restored, user notified |
| incompatible schema major | control messages refused with `schema_incompatible` |

## Consequences

- One engine process keeps per-frame overhead at ~5–6 ms and makes ordering
  trivial; a future GPU model may move perception to its own process.
- The renderer pipeline depends on Chromium's `MediaStreamTrackProcessor`; the
  worker falls back to receiving the track itself if the processor is only
  exposed in workers.
- Native WGC capture bypasses the renderer; when it is used, the viewer has no
  frame bitmaps (overlays only) unless a preview path is added.

## Alternatives considered

- **Perception in the renderer (WASM/WebGPU):** keeps frames in-process but
  ties CV to the UI's event loop and makes ONNX/GPU provider choice harder.
- **Shared memory between capture and engine:** lower copy cost, but more
  platform-specific code; loopback WebSocket measured at ~2 ms transport for
  2.7 MB packets, well inside the latency budget.
- **Separate microservices per stage:** clearer isolation but extra hops and
  serialization per frame for no functional gain at this stage.
