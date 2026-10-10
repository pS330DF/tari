import math

import numpy as np
import pytest

from helpers import renderer
from tari_perception import FrameView, PerceptionPipeline, Projection
from tari_schema import PerceptionSettings, decode_frame_packet
from tari_synth import FrameSpec, SynthTarget, build_packet


def frame(spec: FrameSpec, w=1920, h=1080, **pkt):
    rgba, gt = renderer(w, h).render(spec)
    header, payload = decode_frame_packet(build_packet(rgba, 0, spec.t_ms, **pkt))
    return FrameView.from_packet(header, payload), gt


# -- geometry -------------------------------------------------------------------

def test_projection_angles_are_consistent():
    p = Projection(1920, 1080, 103.0)
    assert p.yaw_of(1920) == pytest.approx(51.5, abs=1e-6)
    assert p.yaw_of(960) == 0.0
    dx, dy = p.angular_offset((960, 540), (960 + p.focal_px * math.tan(math.radians(2.0)), 540))
    assert dx == pytest.approx(2.0, abs=1e-6) and dy == 0.0
    # content moving left means the view turned right
    yaw, pitch = p.shift_to_rotation(-10.0, 5.0)
    assert yaw > 0 and pitch > 0


# -- crosshair --------------------------------------------------------------------

@pytest.mark.parametrize("offset", [(0, 0), (3, -2), (-17, 11)])
@pytest.mark.parametrize("gap", [4.0, 9.0])
def test_crosshair_detected_with_offset_and_gap(offset, gap):
    fv, gt = frame(FrameSpec(t_ms=1, crosshair_offset=offset, crosshair_gap=gap))
    obs = PerceptionPipeline().crosshair.analyze(fv)
    assert obs.method == "detected" and obs.confidence > 0.9 and obs.arms_found == 4
    assert obs.position.x * 1920 == pytest.approx(gt.crosshair_px[0], abs=0.6)
    assert obs.position.y * 1080 == pytest.approx(gt.crosshair_px[1], abs=0.6)
    assert obs.arm_gap_px == pytest.approx(round(gap), abs=0.6)


def test_white_crosshair_needs_matching_setting():
    spec = FrameSpec(t_ms=1, crosshair_color=(255, 255, 255))
    fv, _ = frame(spec)
    assert PerceptionPipeline().crosshair.analyze(fv).method == "assumed_center"
    pipe = PerceptionPipeline(PerceptionSettings(crosshair_color="#ffffff"))
    assert pipe.crosshair.analyze(fv).method == "detected"


def test_missing_crosshair_is_reported_as_estimate_not_observation():
    fv, _ = frame(FrameSpec(t_ms=1, draw_crosshair=False))
    obs = PerceptionPipeline().crosshair.analyze(fv)
    assert obs.method == "assumed_center"
    assert obs.confidence < 0.5
    assert obs.arm_gap_px is None


# -- targets -------------------------------------------------------------------------

def test_no_targets_means_no_detections():
    fv, _ = frame(FrameSpec(t_ms=1))
    assert PerceptionPipeline().targets.detect(fv) == []


@pytest.mark.parametrize("color", ["red", "yellow", "purple"])
def test_target_colors_follow_setting(color):
    fv, gt = frame(FrameSpec(t_ms=1, targets=[SynthTarget(1, -6.0, 1.0, 12.0)], target_color=color))
    pipe = PerceptionPipeline(PerceptionSettings(target_color=color))
    dets = pipe.targets.detect(fv)
    assert len(dets) == 1
    other = "yellow" if color != "yellow" else "red"
    assert PerceptionPipeline(PerceptionSettings(target_color=other)).targets.detect(fv) == []


def test_head_localization_accuracy_away_from_crosshair():
    rng = np.random.default_rng(1)
    pipe = PerceptionPipeline()
    errs = []
    for _ in range(40):
        yaw, pitch, dist = rng.uniform(-20, 20), rng.uniform(-6, 6), rng.uniform(6, 35)
        if abs(yaw) < 2.5:
            yaw += 5.0
        fv, gt = frame(FrameSpec(t_ms=1, targets=[SynthTarget(1, yaw, pitch, dist)]))
        dets = pipe.targets.detect(fv)
        assert len(dets) == 1
        t = gt.targets[0]
        errs.append(math.hypot(dets[0].head.x * 1920 - t.head_px[0], dets[0].head.y * 1080 - t.head_px[1]) / t.head_r_px)
    assert np.percentile(errs, 95) < 1.0  # within one head radius


def test_head_refined_on_full_resolution_crop_near_crosshair():
    fv, gt = frame(FrameSpec(t_ms=1, targets=[SynthTarget(1, 1.6, 1.0, 14.0)]))
    pipe = PerceptionPipeline()
    pipe.crosshair.analyze(fv)
    det = pipe.targets.detect(fv, [pipe.crosshair.occluder_zone()])[0]
    t = gt.targets[0]
    assert det.head_method == "refined_crop"
    assert math.hypot(det.head.x * 1920 - t.head_px[0], det.head.y * 1080 - t.head_px[1]) < 0.5 * t.head_r_px


# -- ego motion ------------------------------------------------------------------------

@pytest.mark.parametrize("dyaw,dpitch", [(0.8, 0.0), (-1.5, 0.4), (3.0, -1.0)])
def test_view_rotation_recovered_from_pixels(dyaw, dpitch):
    pipe = PerceptionPipeline()
    proj = Projection(1920, 1080, 103.0)
    a, _ = frame(FrameSpec(t_ms=1000.0))
    b, _ = frame(FrameSpec(t_ms=1033.3, view_yaw=dyaw, view_pitch=dpitch))
    assert pipe.ego.estimate(a, proj) is None
    m = pipe.ego.estimate(b, proj)
    assert m is not None and m.measurable
    yaw = m.view_rate_dps.x * m.interval_ms / 1000.0
    pitch = m.view_rate_dps.y * m.interval_ms / 1000.0
    assert yaw == pytest.approx(dyaw, abs=0.12)
    assert pitch == pytest.approx(dpitch, abs=0.12)


def test_ego_motion_resets_on_geometry_change():
    pipe = PerceptionPipeline()
    a, _ = frame(FrameSpec(t_ms=1000.0))
    b, _ = frame(FrameSpec(t_ms=1033.0), w=1280, h=720)
    assert pipe.ego.estimate(a, Projection(1920, 1080)) is None
    assert pipe.ego.estimate(b, Projection(1280, 720)) is None


def test_featureless_frames_are_unmeasurable():
    from tari_schema import decode_frame_packet as dec

    pipe = PerceptionPipeline()
    flat = np.full((1080, 1920, 4), 90, dtype=np.uint8)
    flat[..., 3] = 255
    proj = Projection(1920, 1080)
    for i, ts in enumerate((1000.0, 1033.0)):
        header, payload = dec(build_packet(flat, i, ts))
        m = pipe.ego.estimate(FrameView.from_packet(header, payload), proj)
    assert m is not None and not m.measurable
    assert m.confidence <= 0.3


# -- environment + HUD -------------------------------------------------------------------

@pytest.mark.parametrize("w,h", [(1920, 1080), (2560, 1440), (1280, 720), (3840, 2160)])
def test_fiducial_and_hud_read_at_multiple_resolutions(w, h):
    fv, _ = frame(FrameSpec(t_ms=1, ammo=7, timer=63, drill=2), w=w, h=h)
    pipe = PerceptionPipeline()
    env = pipe.environment.detect(fv)
    assert env.kind == "training_lab" and env.map_id == "lab_range_v1"
    hud = pipe.hud.parse(fv, env)
    vals = {r.name: r.value for r in hud.readouts}
    assert vals == {"ammo": 7, "timer": 63, "drill": 2}


def test_missing_fiducial_means_unknown_environment_and_no_hud():
    fv, _ = frame(FrameSpec(t_ms=1, draw_fiducial=False))
    pipe = PerceptionPipeline()
    env = pipe.environment.detect(fv)
    assert env.kind == "unknown"
    assert pipe.hud.parse(fv, env) is None


def test_hidden_hud_readouts_are_invalid_not_guessed():
    fv, _ = frame(FrameSpec(t_ms=1, draw_hud=False))
    pipe = PerceptionPipeline()
    env = pipe.environment.detect(fv)
    hud = pipe.hud.parse(fv, env)
    assert all(r.value is None for r in hud.readouts)


# -- pipeline gating & failure isolation ---------------------------------------------------

def test_gate_restricts_analysis_to_environment_check():
    fv, _ = frame(FrameSpec(t_ms=1, targets=[SynthTarget(1, 3, 0, 12)]))
    res = PerceptionPipeline().process(fv, 1.0, gate=lambda env: False)
    assert res.targets == [] and res.crosshair is None and res.hud is None
    states = {m.name: m.state for m in res.modules}
    assert states["targets"] == "skipped" and states["environment"] == "ok"


def test_failing_module_reports_failure_without_fabrication():
    fv, _ = frame(FrameSpec(t_ms=1, targets=[SynthTarget(1, 3, 0, 12)]))
    pipe = PerceptionPipeline()

    class Broken:
        name, backend = "targets", "broken"

        def detect(self, frame, occluders=None, overlaps=None):
            raise RuntimeError("model crashed")

    pipe.targets = Broken()
    res = pipe.process(fv, 1.0)
    mod = {m.name: m for m in res.modules}["targets"]
    assert mod.state == "failed" and "model crashed" in mod.detail
    assert res.targets == []
    assert res.crosshair is not None  # other modules still ran
