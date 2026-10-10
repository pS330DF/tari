# Datasets

## `lab/` — real Training Lab recordings (video regression set)

Each folder holds a 20 s, 30 fps, 1280×720 recording of the **real** Training Lab
(Chromium + WebGL, rendered offscreen by `scripts/record-lab.cjs` in its scripted
autotest mode) plus exact per-frame ground truth exported by the Lab itself:

| file | content |
| --- | --- |
| `recording.webm` | VP9 (yuv420p, CRF 22) — lossy on purpose, to exercise chroma subsampling |
| `gt.jsonl` | one JSON object per frame: crosshair, camera yaw/pitch, bot head position and radius (CSS px), head visibility, ammo/timer/drill, shot/kill/headshot counters |
| `meta.json` | autotest preset and parameters (seed, scripted entry offset, reaction, flick, outcome) |

Presets: `angle_hold_low` (crosshair held 1.4° below head height), `flick_overshoot`
(scripted 1.8° overshoots), `flick_clean`. The recordings are scripted: the Lab's
autopilot plays inside its own simulation. They contain no VALORANT footage.

Regenerate (needs the Lab built):

```bash
pnpm build:lab
apps/desktop/node_modules/.bin/electron scripts/record-lab.cjs --preset angle_hold_low --frames 600 --out /tmp/lab
.venv/bin/python scripts/encode_recording.py /tmp/lab datasets/lab/angle_hold_low
```

`tests/evaluation/test_lab_regression.py` replays them through the engine and checks
detection, timing and coaching outputs against the ground truth.

## `generator/` — deterministic synthetic scenes (simulated)

`tari_synth` renders Training-Lab-style frames with exact ground truth for unit and
integration tests. Frames it produces are tagged `simulated=True`.
