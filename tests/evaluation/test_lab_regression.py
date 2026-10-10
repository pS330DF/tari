"""Video regression: real Training Lab recordings (VP9) replayed through the engine.

Thresholds encode the accuracy measured on these lossy (yuv420p) recordings when
they were made; a regression in perception, temporal measurement or coaching
fails here. Lossless results (PNG) are higher; see docs/metrics.md.
"""

import collections
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_lab_recording import evaluate  # noqa: E402

LAB = Path(__file__).resolve().parents[2] / "datasets" / "lab"


def run(preset: str) -> dict:
    rec = LAB / preset
    if not (rec / "recording.webm").exists():
        pytest.skip(f"recording {preset} not present")
    return evaluate(rec, rec / "recording.webm")


@pytest.fixture(scope="module")
def angle_hold():
    return run("angle_hold_low")


@pytest.fixture(scope="module")
def flick_over():
    return run("flick_overshoot")


@pytest.fixture(scope="module")
def flick_clean():
    return run("flick_clean")


def test_environment_hud_and_crosshair_are_exact(angle_hold, flick_over, flick_clean):
    for r in (angle_hold, flick_over, flick_clean):
        assert r["environment_detect_rate"] == 1.0
        assert r["hud_exact_rate"] == 1.0
        assert r["crosshair_detect_rate"] == 1.0
        assert r["crosshair_err_px"]["p95"] <= 0.5


def test_head_localization(angle_hold, flick_over, flick_clean):
    for r in (angle_hold, flick_over, flick_clean):
        assert r["head_recall"] >= 0.9
        assert r["head_err_px_no_overlap"]["p95"] <= 4.0


def test_every_visible_target_is_an_exposure(angle_hold, flick_over, flick_clean):
    for r in (angle_hold, flick_over, flick_clean):
        assert r["exposures"] == r["bots_spawned_gt"]


def test_entry_placement_matches_scripted_offset(angle_hold):
    assert angle_hold["entry_vertical_deg_median"] == pytest.approx(angle_hold["configured_entry_pitch_deg"], abs=0.15)
    assert "aim.placement.low" in angle_hold["recommendations"]


def test_acquisition_times_within_one_frame(angle_hold, flick_over, flick_clean):
    frame = 1000 / 30
    for r in (angle_hold, flick_over, flick_clean):
        measured, gt = r["acquisition_ms_measured"], r["acquisition_ms_gt"]
        assert len(measured) >= len(gt) - 2
        # Compare medians (per-target pairing is not exported by the Lab).
        assert abs(statistics.median(measured) - statistics.median(gt)) <= frame + 1


def test_overshoot_detection_without_false_positives(angle_hold, flick_over, flick_clean):
    over = collections.Counter(flick_over["flick_outcomes"])
    resolved = over["overshoot"] + over["clean"] + over["undershoot"]
    assert over["overshoot"] / resolved >= 0.7  # 10/13 on VP9 (13/13 lossless)
    assert "aim.flick.overshoot" in flick_over["recommendations"]
    for r in (angle_hold, flick_clean):
        assert "overshoot" not in r["flick_outcomes"]
    assert flick_clean["recommendations"] == []  # nothing to correct -> no feedback


def test_shots_and_attribution(angle_hold, flick_over, flick_clean):
    for r in (angle_hold, flick_over, flick_clean):
        assert r["shots_detected"] >= r["shots_gt"] - 1  # the last shot may fall past the end of the clip
        known = r["shot_on_head_known"]
        assert known >= r["shots_detected"] - 2
        assert r["shot_on_head_agree_gt"] >= known - 2


def test_pipeline_latency(angle_hold):
    assert angle_hold["pipeline_ms"]["p95"] < 25
