"""Benchmark: per-stage engine latency on synthetic Training-Lab frames.

Measures perception (per module), state update and coaching for several source
resolutions with the desktop's packet layout (540p analysis frame + 384 px
center crop). Reports p50/p95/p99 and process CPU. Results are written to
tests/performance/results/pipeline.json.

    python tests/performance/bench_pipeline.py [--frames 300]
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import psutil

from tari_coaching import CoachingOrchestrator
from tari_perception import FrameView, PerceptionPipeline
from tari_perception.onnx_backend import available_providers
from tari_schema import CoachingSettings, decode_frame_packet
from tari_state import TemporalStateManager
from tari_synth import SyntheticRenderer, angle_hold, build_packet

OUT = Path(__file__).resolve().parent / "results" / "pipeline.json"


def stats(v: list[float]) -> dict:
    a = np.asarray(v)
    return {"p50": round(float(np.percentile(a, 50)), 3), "p95": round(float(np.percentile(a, 95)), 3),
            "p99": round(float(np.percentile(a, 99)), 3), "mean": round(float(a.mean()), 3), "n": int(a.size)}


def run(width: int, height: int, frames: int) -> dict:
    r = SyntheticRenderer(width, height)
    scen = angle_hold(n=20, entry=(1.0, 1.2), seed=3)
    specs = (scen.specs * (frames // len(scen.specs) + 1))[:frames]
    packets = []
    for i, spec in enumerate(specs):
        rgba, _ = r.render(spec)
        packets.append(build_packet(rgba, i, 1e12 + i * 33.333))
    pipe = PerceptionPipeline()
    mgr = TemporalStateManager("bench")
    coach = CoachingOrchestrator("bench", CoachingSettings())
    proc = psutil.Process()
    proc.cpu_percent(None)
    t_decode, t_perc, t_state, t_coach, t_total = [], [], [], [], []
    modules: dict[str, list[float]] = {}
    wall0 = time.perf_counter()
    for i, pkt in enumerate(packets):
        ts = 1e12 + i * 33.333
        t0 = time.perf_counter()
        header, payload = decode_frame_packet(pkt)
        fv = FrameView.from_packet(header, payload)
        t1 = time.perf_counter()
        p = pipe.process(fv, ts, gate=lambda env: mgr.policy.allows_analysis(env, mgr.environment.field(ts, "")))
        t2 = time.perf_counter()
        state, events, decision = mgr.update(p)
        t3 = time.perf_counter()
        trails = {tid: list(tr.history) for tid, tr in mgr.tracker.tracks.items()}
        coach.process(state, events, decision, (width, height), trails, ts)
        t4 = time.perf_counter()
        t_decode.append((t1 - t0) * 1000)
        t_perc.append((t2 - t1) * 1000)
        t_state.append((t3 - t2) * 1000)
        t_coach.append((t4 - t3) * 1000)
        t_total.append((t4 - t0) * 1000)
        for m in p.modules:
            if m.duration_ms is not None:
                modules.setdefault(m.name, []).append(m.duration_ms)
    wall = time.perf_counter() - wall0
    return {
        "source": f"{width}x{height}",
        "packet_bytes": len(packets[0]),
        "frames": frames,
        "decode_ms": stats(t_decode),
        "perception_ms": stats(t_perc),
        "state_ms": stats(t_state),
        "coaching_ms": stats(t_coach),
        "total_ms": stats(t_total),
        "modules_ms": {k: stats(v) for k, v in modules.items()},
        "max_sustainable_fps": round(frames / wall, 1),
        "cpu_percent_one_core_basis": proc.cpu_percent(None),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=300)
    args = ap.parse_args()
    results = {
        "machine": {"platform": platform.platform(), "processor": platform.processor(), "cpu_count": psutil.cpu_count(),
                    "python": platform.python_version(), "onnx_providers": available_providers()},
        "note": "Synthetic (simulated) Training-Lab frames; OpenCV CPU pipeline. GPU is not used by this pipeline.",
        "targets": {"state_ms": "< 15", "coaching_ms": "< 25", "vision_fps": "10-30"},
        "runs": [run(w, h, args.frames) for (w, h) in ((1280, 720), (1920, 1080), (2560, 1440))],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2) + "\n")
    for r in results["runs"]:
        print(f"{r['source']:>10}  total p50 {r['total_ms']['p50']:6.2f}  p95 {r['total_ms']['p95']:6.2f}  p99 {r['total_ms']['p99']:6.2f} ms"
              f" | perception p95 {r['perception_ms']['p95']:5.2f} | state p95 {r['state_ms']['p95']:5.3f} | coaching p95 {r['coaching_ms']['p95']:5.3f}"
              f" | {r['max_sustainable_fps']} fps max | packet {r['packet_bytes'] / 1e6:.2f} MB")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
