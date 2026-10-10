# Measurements: definitions, methods, and validation

Every number TARI shows is computed from pixels of analyzed frames and carries
the sample count and method below. TARI reports **counts and medians of
measured events**, not accuracy percentages, and never fills gaps with guesses:
when an input is missing the value is `unknown`.

## Geometry

- Angles use a pinhole model with the configured horizontal FOV (default 103°,
  as in VALORANT and the Lab) and square pixels:
  `f = (W/2) / tan(hfov/2)`, `yaw(x) = atan((x - W/2)/f)`, `pitch(y) = atan((H/2 - y)/f)`.
- Assumption: the analyzed frame equals the game viewport (the Lab window is
  frameless for this reason). A windowed capture with borders shifts angles slightly.
- Aim error = head center minus crosshair center, in degrees (x right, y up).

## Perception

| Output | Method |
| --- | --- |
| Environment | ArUco `DICT_4X4_50` id 21 in the Lab's HUD cluster; ROI tracking + periodic full scan; label confirmed after 2 frames, stale after 2 s |
| HUD (drill, ammo, timer) | seven-segment readouts anchored to the marker; segment brightness sampled on the centerline at 3 offsets; dark reference from the panel inside each digit; ±0.06 marker-unit alignment search; any unreadable digit invalidates the readout |
| Crosshair | color-masked arms on the unscaled 384 px center crop, paired by symmetry (4 arms → confidence ≈ 0.97); arm gap = movement-error spread. Not found → frame center as an **estimate** (confidence 0.3), which pauses aim measurements |
| Targets | HSV mask for the enemy highlight preset (red/yellow/purple) on the 540p frame; head = rows above the shoulder line (first row reaching 75% of max width) when they are ≤ 70% of the max width and a body continues below; refined on the full-resolution crop near the crosshair; cuts made by the crosshair are closed inside its footprint only |
| View motion | phase correlation on a 256 px wide grayscale copy with a Hanning window; HUD, crosshair and detected targets (union of current and previous frames) are masked; response < 0.35 or low texture → `unmeasurable`. Rotation and player translation are not separated |

## Temporal measurements

| Metric | Definition | Resolution |
| --- | --- | --- |
| **Exposure / entry error** | first frame where a target's head is reliably localized, its silhouette has stopped widening (fully out of cover), and the crosshair is detected. Late (> 300 ms) exposures get 0.6× confidence | one analyzed frame |
| **Held angle** (`view_settled`) | measured view speed < 15°/s at exposure | — |
| **Acquisition time** | target's first detection → first analyzed frame where the crosshair is within **1.3 × estimated head radius + 0.05°** of the head center (the tolerance absorbs radius/center quantization on heads a few pixels wide); only reliable head estimates count | ± one analyzed-frame interval (reported as `resolution_ms`) |
| **Overshoot** | along the **measured view-motion direction** (only after the view has moved toward the target by ≥ max(1°, ½ of the initial error)): the crosshair passes the head center by more than max(head radius, 0.35°) — plus max(radius/2, 0.2°) while the crosshair overlaps the head — while clearly off the head (> 1.5 radii), on two analyzed frames. A target walking past a still crosshair is not an overshoot | — |
| **Undershoot** | the first movement stopped short by more than max(radius, 0.35°) of where the target *was* (target's own measured motion removed: `e0 − V`) and a second movement followed. Disabled when view motion was unmeasurable during the flick | — |
| **Sub-movements** | segments of view speed > 18°/s separated by < 8°/s | — |
| **Shot** | HUD ammo decrement confirmed by the next readout (a single misread cannot create a shot); timed at the decrement frame | one analyzed frame |
| **On head at shot** | last reliable aim error from the pre-shot frame(s) (≤ 150 ms old, shifted by measured view motion ≤ 0.5°) within the acquisition tolerance; otherwise `unknown` | — |
| **Shot while moving** | crosshair arm gap ≥ max(1.5 px, 25%) above the session's resting gap | — |
| **Shot during view motion** | measured view speed > 40°/s at the shot | — |

"Reliable" head estimate = method `head_profile` or `refined_crop` with
confidence ≥ 0.7. Fallback estimates (`top_ratio`, `blob_top`) are shown but
never drive timing or flick classification.

When view motion is unmeasurable during a fast flick, the flick's view step for
that frame is inferred from the error change (assuming the target held still for
one frame); the count is reported as `inferred_view_frames` on the event.

## Coaching rules (aim)

Rolling window of the last 8 qualifying samples; minimum samples: placement 4
held-angle exposures, acquisition 5, flicks 5, shots 5. Thresholds by strictness:

| Rule | Lenient | Balanced | Strict |
| --- | --- | --- | --- |
| placement low/high (median vertical entry error, ≥ 60% same side) | 1.4° | 0.9° | 0.6° |
| angle preparation (median \|horizontal\| entry error) | 6° | 4° | 2.5° |
| acquisition (median), + skill offset (new +150, advanced −60 ms) | 620 ms | 480 ms | 380 ms |
| overshoot / undershoot share of resolved flicks | 50% | 40% | 30% |
| shots during view motion / while moving share | 50% | 35% | 25% |

Placement rules are skipped while the HUD shows the Flick drill (wide entries
are the exercise there). Recommendation confidence = mean sample confidence ×
min(1, 0.6 + 0.05·n); it is a heuristic certainty score, not a probability.
The filter drops recommendations below `min_confidence` (default 0.5), repeats
of the same rule within the intensity cooldown (60/30/18 s), and non-P0 feedback
within the minimum gap (12/6/3 s) of equal-or-higher-priority feedback.

## Validation results

Machine: Apple M3, 8 GB, macOS 15.2, Python 3.12, OpenCV 5.0 (CPU).

### Synthetic scenes (simulated, `tests/`)

- HUD decoding: 120/120 readouts correct across 10 resolutions (1024×768 … 3840×2160, incl. 21:9), min confidence 0.90.
- Head localization, crosshair clear of the target: p95 1.7 px (0.58 head radii) across 1280–2560 px widths; with the crosshair over a small head p95 ≈ 9.6 px.
- Entry error within 0.25° of ground truth; acquisition time within 1.5 frames; flick outcomes ≥ 4/5 correct per class (unit tests).

### Real Training Lab recordings (`datasets/lab`, 600 frames each, 1280×720, 30 fps)

Rendered by Chromium/WebGL, scripted autopilot, exact per-frame ground truth.

| Recording | Env / HUD / crosshair | Head recall | Head err p95 (clear) | Exposures | Acquisition median meas/GT | Flicks | Shots | On head agrees | Feedback |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| angle_hold_low (lossless) | 100% / 100% / 100% (0 px) | 93.8% | 2.9 px | 9/9 | 400/400 ms | 8 clean | 8/9* | 8/8 | `aim.placement.low` |
| flick_overshoot (lossless) | 100% / 100% / 100% | 96.6% | 1.3 px | 14/14 | 633/633 ms | **13/13 overshoot** | 13/13 | 13/13 | `aim.flick.overshoot`, `aim.acquisition.slow` |
| flick_clean (lossless) | 100% / 100% / 100% | 95.6% | 1.3 px | 16/16 | 433/433 ms | 14 clean, 2 unresolved, **0 false overshoot** | 16/16 | 14/15 (1 unknown) | none |
| angle_hold_low (VP9 4:2:0) | 100% / 100% / 100% | 91.8% | 3.7 px | 9/9 | 400/400 ms | 8 clean | 8/9* | 7/8 | `aim.placement.low` |
| flick_overshoot (VP9) | 100% / 100% / 100% | 96.6% | 2.7 px | 14/14 | 633/633 ms | 10 overshoot, 3 clean | 13/13 | 13/13 | same as lossless |
| flick_clean (VP9) | 100% / 100% / 100% | 95.6% | 2.1 px | 16/16 | 433/433 ms | 14 clean, 2 unresolved | 16/16 | 13/15 | none |

\* the last shot falls past the end of the clip (its confirmation frame is not recorded).
Scripted entry offset 1.4° low → measured median **1.407°**.

### Latency

| Measurement | Result | Target |
| --- | --- | --- |
| Engine per frame (decode + perception + state + coaching), 1280–2560 px sources | p50 5.3 ms, p95 5.7–6.0 ms, ~185 fps single-threaded | vision 10–30 fps |
| State update | p95 0.065 ms | < 15 ms |
| Coaching evaluation | p95 0.03 ms | < 25 ms |
| WebSocket round trip @30 fps (2.7 MB packets) | p50 10.4 ms, p95 11.6 ms | — |
| Overload @400 fps, 64 in flight | 104 fps analyzed, 1,779 frames dropped, p99 26.6 ms (bounded) | stale frames dropped |
| Desktop E2E (real Lab video through the app), frame → result | p50 25 ms, p95 31 ms, p99 36 ms; 29.7 fps analyzed of 30 | — |
| Desktop E2E, frame → feedback drawn | p50 28 ms, p95 46 ms, p99 48 ms | < 150 ms |

Not measured: GPU utilization (no NVML on this machine; reported as unavailable),
voice start latency in E2E (speech is muted in automated runs), any Windows run.

## Known limitations

- A crosshair covering a small head hides it; those frames give fallback head
  estimates that are excluded from timing/flick decisions.
- Very fast flicks in low-texture scenes can make view motion unmeasurable
  (VP9 compression makes this more frequent; see overshoot recall above).
- View motion includes player translation (parallax); it is labelled "view motion".
- Head height is estimated from silhouette geometry; partially occluded heads lower confidence.
- All validation so far uses the Training Lab and synthetic scenes. No VALORANT footage is analyzed.
