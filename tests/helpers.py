"""Shared test helpers: run simulated scenarios through the real pipeline."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from tari_coaching import CoachingOrchestrator
from tari_perception import FrameView, PerceptionPipeline
from tari_schema import CoachingSettings, PerceptionSettings, decode_frame_packet
from tari_state import TemporalStateManager
from tari_synth import Scenario, SyntheticRenderer, build_packet


@dataclass
class Run:
    events: list = field(default_factory=list)
    states: list = field(default_factory=list)
    perceptions: list = field(default_factory=list)
    gts: list = field(default_factory=list)
    recs: list = field(default_factory=list)
    overlays: list = field(default_factory=list)
    voice: list = field(default_factory=list)

    def of(self, kind: str) -> list:
        return [e for e in self.events if e.type == kind]


_RENDERERS: dict[tuple[int, int], SyntheticRenderer] = {}


def renderer(w: int = 1920, h: int = 1080) -> SyntheticRenderer:
    if (w, h) not in _RENDERERS:
        _RENDERERS[(w, h)] = SyntheticRenderer(w, h)
    return _RENDERERS[(w, h)]


def run_scenario(scen: Scenario, coaching: CoachingSettings | None = None, every: int = 1,
                 w: int = 1920, h: int = 1080, perception: PerceptionSettings | None = None,
                 source_label: str = "TARI Training Lab") -> Run:
    r = renderer(w, h)
    pipe = PerceptionPipeline(perception)
    mgr = TemporalStateManager("test", source_label=source_label)
    coach = CoachingOrchestrator("test", coaching or CoachingSettings())
    run = Run()
    for i, spec in enumerate(scen.specs):
        if i % every:
            continue
        rgba, gt = r.render(spec)
        header, payload = decode_frame_packet(build_packet(rgba, i, spec.t_ms))
        fv = FrameView.from_packet(header, payload)
        ts = spec.t_ms
        p = pipe.process(fv, ts, gate=lambda env: mgr.policy.allows_analysis(env, mgr.environment.field(ts, "")))
        state, events, decision = mgr.update(p)
        trails = {tid: list(tr.history) for tid, tr in mgr.tracker.tracks.items()}
        out = coach.process(state, events, decision, (fv.width, fv.height), trails, ts)
        run.events += events
        run.states.append(state)
        run.perceptions.append(p)
        run.gts.append(gt)
        run.recs += out.recommendations
        run.overlays += out.overlays
        run.voice += out.voice
    return run


def gt_acquisition_times(scen: Scenario, run: Run) -> list[float]:
    """Ground-truth acquisition time per exposure: first frame with any part of the target
    out of cover -> first frame with the crosshair on the true head, using the engine's
    documented definition (within 1.3 x head radius + 0.05 deg)."""
    from tari_state.tracker import ACQ_MARGIN_DEG, ACQ_RADIUS_FACTOR

    out = []
    for (t0, t1) in scen.windows:
        vis = acq = None
        for gt in run.gts:
            if not (t0 <= gt.t_ms < t1) or not gt.targets:
                continue
            tt = gt.targets[0]
            bx = tt.bbox_px[0]
            spec_cover_left = None
            for spec in scen.specs:
                if spec.t_ms == gt.t_ms and spec.covers:
                    c = spec.covers[0]
                    r = renderer(gt.width, gt.height)
                    spec_cover_left, _ = r.project(c.yaw0, c.pitch1, spec.view_yaw, spec.view_pitch)
                    break
            visible = spec_cover_left is None or bx < spec_cover_left
            if visible and vis is None:
                vis = gt.t_ms
            d = math.hypot(tt.head_px[0] - gt.crosshair_px[0], tt.head_px[1] - gt.crosshair_px[1])
            f = renderer(gt.width, gt.height).focal
            tol = ACQ_RADIUS_FACTOR * tt.head_r_px + f * math.tan(math.radians(ACQ_MARGIN_DEG))
            if vis is not None and acq is None and d <= tol:
                acq = gt.t_ms
        if vis is not None and acq is not None:
            out.append(acq - vis)
    return out
