"""Evaluate the engine on a real Training Lab recording (scripts/record-lab.cjs).

Every frame is run through perception -> temporal state -> coaching exactly as
in a live session, and compared with the Lab's per-frame ground truth.

    python tests/evaluation/eval_lab_recording.py <recording_dir> [--video file.webm] [--json out.json]

With --video, frames are decoded from a lossy video instead of the lossless
PNGs (to measure robustness to compression / chroma subsampling).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path

import cv2
import numpy as np

from tari_coaching import CoachingOrchestrator
from tari_perception import FrameView, PerceptionPipeline
from tari_schema import CoachingSettings, decode_frame_packet
from tari_state import TemporalStateManager
from tari_state.tracker import ACQ_MARGIN_DEG, ACQ_RADIUS_FACTOR
from tari_synth import build_packet


ROOT = Path(__file__).resolve().parents[2]


def display_path(path: Path) -> str:
    """Repo-relative path for reports (absolute local paths are not written to results)."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return f"<local>/{path.name}"


def pct(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def frames_from(rec: Path, video: Path | None):
    if video is None:
        for p in sorted(rec.glob("frame_*.png")):
            yield cv2.imread(str(p), cv2.IMREAD_COLOR)
    else:
        cap = cv2.VideoCapture(str(video))
        while True:
            ok, img = cap.read()
            if not ok:
                break
            yield img
        cap.release()


def evaluate(rec: Path, video: Path | None = None) -> dict:
    meta = json.loads((rec / "meta.json").read_text())
    gts = [json.loads(line) for line in (rec / "gt.jsonl").read_text().splitlines() if line.strip()]
    fps = float(meta["config"]["fps"])
    pipe = PerceptionPipeline()
    mgr = TemporalStateManager("eval", source_label="TARI Training Lab")
    coach = CoachingOrchestrator("eval", CoachingSettings())
    t0_wall = time.time() * 1000.0

    env_ok = hud_ok = hud_total = 0
    cross_err: list[float] = []
    cross_found = 0
    head_err: list[float] = []
    head_err_r: list[float] = []
    head_err_overlap: list[float] = []
    head_hits = head_total = 0
    timings: list[float] = []
    events = []
    recs = []
    n = 0
    for i, (bgr, gt) in enumerate(zip(frames_from(rec, video), gts)):
        if bgr is None:
            break
        n += 1
        rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
        h, w = rgba.shape[:2]
        scale = w / gt["viewport"]["w"]
        ts = t0_wall + gt["t_ms"]
        header, payload = decode_frame_packet(build_packet(rgba, i, ts, session_id="eval"))
        fv = FrameView.from_packet(header, payload)
        t_start = time.perf_counter()
        p = pipe.process(fv, ts, gate=lambda env: mgr.policy.allows_analysis(env, mgr.environment.field(ts, "")))
        state, evs, decision = mgr.update(p)
        trails = {tid: list(tr.history) for tid, tr in mgr.tracker.tracks.items()}
        out = coach.process(state, evs, decision, (w, h), trails, ts)
        timings.append((time.perf_counter() - t_start) * 1000)
        events += evs
        recs += out.recommendations

        if p.environment and p.environment.kind == "training_lab":
            env_ok += 1
        if p.hud:
            vals = {r.name: r.value for r in p.hud.readouts}
            expected = {"ammo": gt["ammo"], "timer": gt["timer"], "drill": 1 if gt["drill"] == "angle_hold" else 2}
            hud_total += 1
            hud_ok += int(vals == expected)
        cx, cy = gt["crosshair_css"]["x"] * scale, gt["crosshair_css"]["y"] * scale
        if p.crosshair and p.crosshair.method == "detected":
            cross_found += 1
            cross_err.append(math.hypot(p.crosshair.position.x * w - cx, p.crosshair.position.y * h - cy))
        bot = gt.get("bot")
        if bot and bot["head_visible"] and bot["on_screen"] and bot["phase"] != "dead":
            head_total += 1
            hx, hy = bot["head_css"]["x"] * scale, bot["head_css"]["y"] * scale
            r = max(0.5, bot["head_radius_css"] * scale)
            best = min((math.hypot(d.head.x * w - hx, d.head.y * h - hy) for d in p.targets), default=None)
            if best is not None and best <= max(3 * r, 6.0):
                head_hits += 1
                overlap = math.hypot(hx - cx, hy - cy) < r + 14 * scale
                (head_err_overlap if overlap else head_err).append(best)
                if not overlap:
                    head_err_r.append(best / r)

    def of(kind: str) -> list:
        return [e for e in events if e.type == kind]

    # Ground-truth exposures/acquisitions from the Lab's own state.
    gt_acq: list[float] = []
    vis_start: dict[int, float] = {}
    bot_id = 0
    last_phase = None
    acquired = False
    for gt in gts[:n]:
        bot = gt.get("bot")
        phase = bot["phase"] if bot else None
        if bot and (last_phase in (None, "hidden", "dead")) and phase in ("emerging", "standing"):
            bot_id += 1
            acquired = False
        last_phase = phase
        if not bot or not bot["head_visible"] or not bot["on_screen"]:
            continue
        if bot_id not in vis_start:
            vis_start[bot_id] = gt["t_ms"]
        cx, cy = gt["crosshair_css"]["x"], gt["crosshair_css"]["y"]
        d = math.hypot(bot["head_css"]["x"] - cx, bot["head_css"]["y"] - cy)
        f = (gt["viewport"]["w"] / 2) / math.tan(math.radians(51.5))
        if not acquired and d <= ACQ_RADIUS_FACTOR * bot["head_radius_css"] + f * math.tan(math.radians(ACQ_MARGIN_DEG)):
            acquired = True
            gt_acq.append(gt["t_ms"] - vis_start[bot_id])

    # Shot attribution vs ground truth: the Lab knows whether each shot was a headshot kill.
    shot_eval = []
    gt_by_frame = {g["frame"]: g for g in gts[:n]}
    for e in of("shot_fired"):
        g, prev = gt_by_frame.get(e.frame_id), gt_by_frame.get(e.frame_id - 1)
        if g is None or prev is None or "headshots" not in g:
            continue
        gt_head = g["headshots"] > prev["headshots"]
        shot_eval.append({"frame": e.frame_id, "on_head_measured": e.on_head, "headshot_gt": gt_head})
    known = [s for s in shot_eval if s["on_head_measured"] is not None]
    exposed = of("target_exposed")
    settled_y = [e.entry_error_deg.y for e in exposed if e.view_settled]
    gt_shots = gts[min(n, len(gts)) - 1]["shots"] if n else 0
    report = {
        "recording": display_path(rec),
        "source": "video:" + display_path(video) if video else "png (lossless)",
        "preset": meta["preset"],
        "config": meta["config"],
        "frames": n,
        "resolution": f"{w}x{h}",
        "environment_detect_rate": round(env_ok / n, 4) if n else None,
        "hud_exact_rate": round(hud_ok / hud_total, 4) if hud_total else None,
        "crosshair_detect_rate": round(cross_found / n, 4) if n else None,
        "crosshair_err_px": {"p50": pct(cross_err, 50), "p95": pct(cross_err, 95), "max": max(cross_err) if cross_err else None},
        "head_recall": round(head_hits / head_total, 4) if head_total else None,
        "head_frames": head_total,
        "head_err_px_no_overlap": {"p50": pct(head_err, 50), "p95": pct(head_err, 95), "n": len(head_err)},
        "head_err_radii_no_overlap": {"p50": pct(head_err_r, 50), "p95": pct(head_err_r, 95)},
        "head_err_px_crosshair_overlap": {"p50": pct(head_err_overlap, 50), "p95": pct(head_err_overlap, 95), "n": len(head_err_overlap)},
        "bots_spawned_gt": bot_id,
        "exposures": len(exposed),
        "acquisitions": len(of("target_acquired")),
        "acquisition_ms_measured": [round(e.acquisition_ms) for e in of("target_acquired")],
        "acquisition_ms_gt": [round(a) for a in gt_acq],
        "entry_vertical_deg_settled": [round(v, 2) for v in settled_y],
        "entry_vertical_deg_median": round(statistics.median(settled_y), 3) if settled_y else None,
        "configured_entry_pitch_deg": meta["config"].get("entryPitchDeg"),
        "flick_outcomes": [e.outcome for e in of("flick_analyzed")],
        "shots_detected": sum(e.shots for e in of("shot_fired")),
        "shot_on_head_known": len(known),
        "shot_on_head_agree_gt": sum(1 for s in known if s["on_head_measured"] == s["headshot_gt"]),
        "shot_on_head_unknown": len(shot_eval) - len(known),
        "shots_gt": gt_shots,
        "recommendations": [r.rule_id for r in recs],
        "pipeline_ms": {"p50": pct(timings, 50), "p95": pct(timings, 95), "p99": pct(timings, 99)},
        "frame_interval_ms": round(1000 / fps, 2),
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", type=Path)
    ap.add_argument("--video", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    report = evaluate(args.recording, args.video)
    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n")


if __name__ == "__main__":
    main()
