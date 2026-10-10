# Implementation status

Legend: **Done** = implemented and verified here · **Partial** = implemented with
stated gaps · **Not verified** = written but not executed in this environment ·
**Not started**.

Development machine: macOS 15.2 (Apple M3). Windows was not available, and this
process had no macOS Screen Recording permission, so OS-level screen capture
could not be exercised (see "Verification gaps").

## Vertical slice (spec §18)

| Step | Status | Evidence |
| --- | --- | --- |
| 1 Launch the application | Done (macOS) | Electron app builds and runs; engine auto-starts via supervisor |
| 2 Select a capture source | Partial | source picker over `desktopCapturer` (window/screen) and video files; listing failed here for lack of Screen Recording permission (handled with an actionable message) |
| 3 Continuous frame stream | Done (video-file path) | `MediaStreamTrackProcessor` → worker; 30 fps source in the E2E run |
| 4 Display the stream | Done | viewer draws each analyzed frame with its overlays (E2E screenshots) |
| 5 Perception pipeline | Done | environment, HUD, crosshair, targets, view motion |
| 6 Typed observation events | Done | `tari_schema` events, generated TS types |
| 7 Deterministic coaching | Done | aim coach rules + priority/confidence filter |
| 8 Synchronized feedback in the viewer | Done | frame + overlay pairing, live-mode TTL gating |
| 9 Processing latency | Done | per-stage engine telemetry + client e2e/visual latency |
| 10 Save session data locally | Done | SQLite sessions/events/recommendations/metrics/perf |

Desktop E2E run (`TARI_E2E_VIDEO`): 532 results from 30 fps real-Lab video,
29.7 fps analyzed, frame→result p95 31 ms, frame→screen p95 46 ms, 8/8
exposures, correct placement feedback, session persisted.

## Roadmap phases

| Phase | Item | Status |
| --- | --- | --- |
| 1 | Electron desktop app, typed IPC, settings persistence | Done |
| 1 | Capture adapter (Electron desktopCapturer / video file) | Done (video file verified; desktopCapturer not verified here) |
| 1 | Native WGC capture service (Rust) | Not verified: compiles for `x86_64-pc-windows-msvc`; protocol verified against the live engine with `tari-capture synthetic`; never run on Windows |
| 1 | Frame scheduler (bounded, stale drop) | Done (unit + overload benchmark) |
| 1 | Telemetry (fps, latency p50/95/99, queue, frame age, CPU, memory) | Done; GPU utilization reported as unavailable (no NVML here, Electron exposes none) |
| 1 | Structured event bus / logs | Done (typed events over the stream, JSON-lines logs in engine and desktop) |
| 2 | HUD detection | Done for the Training Lab HUD profile; no OCR engine for real game HUDs |
| 2 | Crosshair calibration | Done (color + arm symmetry, gap measurement) |
| 2 | Target detection | Done (color segmentation + head geometry); ONNX adapter ready, no model trained |
| 2 | Map identification | Partial: Lab map id from the fiducial; no VALORANT map/minimap analyzer |
| 2 | Agent identification | Not started (state reports `unknown` with reason) |
| 2 | Timestamps, confidence scoring | Done |
| 3 | Aim rules, placement analysis, state management, priority/confidence filter, overlay instructions | Done |
| 4 | Spatial guidance: map calibration, utility markers, projection alignment, placement validation | Not started |
| 5 | Tactical evaluation, agent knowledge base, coordination planning | Not started |
| 6 | Voice output (local TTS, priority/interrupt/dedupe) | Done (Web Speech API; latency instrumented, muted in automated runs) |
| 6 | Speech recognition, VAD, conversational replies, callout coaching | Not started |
| 7 | Player profile, persistent metrics, skill trends, weakness-based next focus | Done (trends need ≥ 3 validated sessions) |
| 7 | Adaptive training plans | Not started |
| 8 | Integration tests, video regression tests, accuracy tests, latency benchmarks | Done |
| 8 | Overlay alignment tests | Partial (instruction/frame binding and viewport mapping tested; no pixel-level screenshot comparison) |
| 8 | Privacy audit, compliance review | Done as documents (`docs/compliance.md`); no external review |

## Coaching domains (spec §1)

| Domain | Streaming implementation |
| --- | --- |
| Aim and crosshair placement | **Live** (Training Lab) |
| Abilities / utility | Not started |
| Positioning / movement | Partial: movement-error and view-motion signals feed aim rules; no positioning coach |
| Tactical decisions | Not started |
| Agent mastery | Not started |
| Team coordination | Not started |
| Voice communication / briefings | Not started (voice *output* exists) |

The engine advertises these honestly: `coaching_domains_live: ["aim"]`,
everything else in `coaching_domains_planned`.

## Interfaces (spec §14)

FramePacket, PerceptionResult, Observation (as `StateField` provenance on every
GameState field), GameState, CoachingEvent, CoachingRecommendation,
OverlayInstruction, VoiceInstruction, PlayerProfile, PerformanceMetric /
PerformanceSnapshot — all versioned (schema 1.0.0) with explicit timestamps.

## Tests (spec §16)

| Required case | Test |
| --- | --- |
| Dropped frames | `test_state_engine.py::test_dropped_frames_keep_measurements_consistent`, scheduler tests (Python + TS) |
| Delayed frames | `test_engine_components.py::test_drop_reason_stale_and_out_of_order`, stream stale test |
| Capture interruptions | `test_resolution_change_resets_tracking` (capture gap), disconnect test |
| Window resizing / resolution changes | same test (`resolution_changed`), multi-resolution HUD/crosshair tests |
| Incorrect agent identification | `test_categorical_hysteresis_rejects_single_misidentification` (generic categorical hysteresis; no agent recognizer yet) |
| Missing HUD elements | `test_hud_missing_disables_shots_but_not_aim_measurement`, `test_hidden_hud_readouts_are_invalid_not_guessed` |
| Low-confidence observations | `test_missing_crosshair_is_reported_as_estimate_not_observation`, filter tests |
| Stale coaching events | overlay TTL tests (TS), voice TTL test, recommendation expiry |
| Duplicate voice feedback | `voice.test.ts` (dedupe/cooldown), filter dedupe test |
| Unavailable GPU | `test_provider_selection_prefers_gpu_and_falls_back_to_cpu`, GPU telemetry unavailable reason |
| Network loss | `test_disconnect_finalizes_session`; worker reconnect logic (not automated) |
| Invalid model output | `test_invalid_model_output_rejected`, `test_onnx_detector_with_invalid_output_yields_failure_not_detections` |
| Database corruption | `test_corrupt_database_is_quarantined_not_deleted`, `test_corrupt_database_reported_to_client` |
| Model version changes | `test_registry_rejects_missing_mismatched_and_incompatible_models`, `test_registry_version_change_is_refused` |

Counts at the time of writing: Python 108 passed (incl. 8 real-Lab video regressions), TypeScript 38 passed (desktop 20, lab 6, shared-types 5, overlay 4, telemetry 3), Rust 5 passed; all TypeScript projects typecheck; the WGC module type-checks for Windows.

## Verification gaps (could not be executed here)

- Any Windows 11 run: desktop app, Chromium's capture backend on Windows,
  title-bar overlay, Korean SAPI voices, packaging.
- `desktopCapturer` window/screen capture on this Mac (no Screen Recording
  permission was granted to the process). The identical downstream pipeline was
  verified with the video-file source.
- Native WGC service at runtime (only compile-checked; its wire protocol was
  exercised against the live engine on macOS with synthetic frames).
- Interactive play in the Lab by a person (validated via scripted autotest
  recordings rendered by the real Lab).
- `electron-builder` Windows installer and a bundled Python runtime.

## Not implemented yet (by design of this first slice)

Mode B transparent overlay window over the game/Lab, agent/ability/minimap
recognition, utility/positioning/tactical/team/communication coaches, speech
recognition and conversation, LLM explanations, knowledge base content,
adaptive training plans, history deletion UI, installer, auto-update.
