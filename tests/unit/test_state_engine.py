import statistics

import pytest

from helpers import gt_acquisition_times, run_scenario
from tari_schema import EnvironmentObservation, TextField
from tari_state import CategoricalTracker, IntegrationPolicy, ShotDetector
from tari_state.policy import AuthorizationResult
from tari_synth import ExposurePlan, angle_hold, build_scenario, flicks


@pytest.fixture(scope="module")
def low_run():
    scen = angle_hold(n=6, entry=(1.0, 1.4), seed=4)
    return scen, run_scenario(scen)


def test_every_exposure_produces_the_full_event_chain(low_run):
    scen, run = low_run
    n = len(scen.plans)
    assert len(run.of("target_exposed")) == n
    assert len(run.of("target_acquired")) == n
    assert len(run.of("flick_analyzed")) == n
    assert len(run.of("shot_fired")) == n
    assert len(run.of("target_lost")) == n


def test_entry_error_matches_ground_truth(low_run):
    scen, run = low_run
    measured = [e.entry_error_deg.y for e in run.of("target_exposed")]
    planned = [p.entry[1] for p in scen.plans]
    for m, p in zip(measured, planned):
        assert m == pytest.approx(p, abs=0.25)
    assert all(e.view_settled for e in run.of("target_exposed"))


def test_acquisition_time_within_one_frame_of_ground_truth(low_run):
    scen, run = low_run
    gt = gt_acquisition_times(scen, run)
    measured = [e.acquisition_ms for e in run.of("target_acquired")]
    assert len(gt) == len(measured)
    frame = 1000.0 / scen.fps
    for m, g in zip(measured, gt):
        assert abs(m - g) <= frame * 1.5 + 1e-6


def test_events_are_timestamped_by_source_frame(low_run):
    _, run = low_run
    frame_ts = {p.frame_id: p.acquired_ts_ms for p in run.perceptions}
    for e in run.events:
        assert e.ts_ms == frame_ts[e.frame_id]


@pytest.mark.parametrize("outcome,expected", [("overshoot", "overshoot"), ("undershoot", "undershoot"), ("clean", "clean")])
def test_flick_outcome_classification(outcome, expected):
    run = run_scenario(flicks(n=5, outcome=outcome, seed=2))
    outcomes = [e.outcome for e in run.of("flick_analyzed")]
    assert len(outcomes) == 5
    assert sum(o == expected for o in outcomes) >= 4, outcomes
    if outcome == "overshoot":
        over = [e.overshoot_deg for e in run.of("flick_analyzed") if e.outcome == "overshoot"]
        assert statistics.median(over) == pytest.approx(1.6, abs=0.35)


def test_moving_shots_flagged_from_crosshair_spread():
    scen = angle_hold(n=5, entry=(0.8, 0.2), moving_at_shot=True, seed=8)
    run = run_scenario(scen)
    shots = run.of("shot_fired")
    assert len(shots) == 5
    assert all(s.movement_error is True for s in shots)
    still = run_scenario(angle_hold(n=3, entry=(0.8, 0.2), seed=8))
    assert all(s.movement_error is False for s in still.of("shot_fired"))


def test_dropped_frames_keep_measurements_consistent(low_run):
    scen, full = low_run
    half = run_scenario(scen, every=2)  # simulate 50% frame drop (15 fps analysis)
    assert len(half.of("target_exposed")) == len(scen.plans)
    acq_full = [e.acquisition_ms for e in full.of("target_acquired")]
    acq_half = [e.acquisition_ms for e in half.of("target_acquired")]
    for a, b in zip(acq_full, acq_half):
        assert abs(a - b) <= 2 * 1000.0 / scen.fps + 1e-6
    assert all(e.resolution_ms == pytest.approx(2000.0 / scen.fps, abs=0.5) for e in half.of("target_acquired"))


def test_resolution_change_resets_tracking():
    plans = [ExposurePlan(tid=1, entry=(1.0, 0.5))]
    a = build_scenario("a", plans)
    run = run_scenario(a)
    reconf = run.of("source_reconfigured")
    assert reconf[0].reason == "session_start"
    from helpers import renderer
    from tari_coaching import CoachingOrchestrator
    from tari_perception import FrameView, PerceptionPipeline
    from tari_schema import CoachingSettings, decode_frame_packet
    from tari_state import TemporalStateManager
    from tari_synth import FrameSpec, build_packet

    pipe, mgr = PerceptionPipeline(), TemporalStateManager("t")
    events = []
    for i, (w, h, t) in enumerate([(1920, 1080, 0), (1920, 1080, 33), (1280, 720, 66), (1280, 720, 1500)]):
        rgba, _ = renderer(w, h).render(FrameSpec(t_ms=1000 + t))
        header, payload = decode_frame_packet(build_packet(rgba, i, 1000 + t))
        _, ev, _ = mgr.update(pipe.process(FrameView.from_packet(header, payload), 1000 + t))
        events += [e for e in ev if e.type == "source_reconfigured"]
    assert [e.reason for e in events] == ["session_start", "resolution_changed", "capture_gap"]
    assert events[2].gap_ms == pytest.approx(1434.0, abs=1)
    del CoachingOrchestrator, CoachingSettings


def test_unverified_source_is_restricted_and_not_analyzed():
    scen = angle_hold(n=2, entry=(1.0, 1.0))
    for spec in scen.specs:
        spec.draw_fiducial = False
    run = run_scenario(scen, source_label="VALORANT")
    assert run.of("target_exposed") == []
    assert all(s.coaching_mode == "restricted" for s in run.states)
    assert all(s.targets == [] for s in run.states)
    assert run.recs == [] and run.overlays == []
    assert all(p.targets == [] for p in run.perceptions)


def test_hud_missing_disables_shots_but_not_aim_measurement():
    scen = angle_hold(n=3, entry=(1.0, 1.2))
    for spec in scen.specs:
        spec.draw_hud = False
    run = run_scenario(scen)
    assert run.of("shot_fired") == []
    assert len(run.of("target_exposed")) == 3
    notices = run.of("perception_notice")
    assert any(n.module == "hud" for n in notices)
    assert all(s.ammo.status == "unknown" for s in run.states)


def test_missing_crosshair_pauses_measurements_with_notice():
    scen = angle_hold(n=2, entry=(1.0, 1.2))
    for spec in scen.specs:
        spec.draw_crosshair = False
    run = run_scenario(scen)
    assert run.of("target_exposed") == []
    assert all(s.crosshair.status == "estimated" for s in run.states if s.coaching_mode == "live_training")
    assert any(n.module == "crosshair" for n in run.of("perception_notice"))


# -- unit-level state helpers ----------------------------------------------------------

def test_categorical_hysteresis_rejects_single_misidentification():
    cat = CategoricalTracker("agent", "test", confirm_n=3)
    for t in range(5):
        cat.update("jett", 0.9, t * 33.0)
    assert cat.value == "jett"
    cat.update("reyna", 0.9, 200.0)  # one wrong frame
    cat.update("jett", 0.9, 233.0)
    assert cat.value == "jett"
    for t in range(3):
        cat.update("reyna", 0.9, 300.0 + t * 33)
    assert cat.value == "reyna"
    low = CategoricalTracker("agent", "test")
    for t in range(10):
        low.update("sage", 0.3, t * 33.0)  # low-confidence observations never confirm
    assert low.value is None and low.field(400.0, "m").status == "unknown"


def test_categorical_goes_stale():
    cat = CategoricalTracker("environment", "fiducial", confirm_n=1, ttl_ms=2000)
    cat.update("training_lab", 0.95, 0.0)
    assert cat.field(1000.0, "m").status == "observed"
    f = cat.field(2500.0, "m")
    assert f.status == "stale" and f.value == "training_lab" and f.reason


def test_shot_detector_ignores_single_frame_misreads():
    d = ShotDetector()
    seq = [25, 25, 19, 25, 25, 24, 24, 23, 23, 25]  # 19 is a misread; 25 at end is a reload
    shots = []
    for i, v in enumerate(seq):
        shots += d.update(v, 0.95, i * 33.0, i, {})
    assert [s.shots for s in shots] == [1, 1]
    assert [s.frame_id for s in shots] == [5, 7]
    assert d.update(None, 0.0, 999, 99, {}) == []


def test_policy_requires_observed_lab_and_never_grants_riot_access():
    pol = IntegrationPolicy()
    lab = TextField(status="observed", value="training_lab", confidence=0.95, updated_ts_ms=1000.0)
    assert pol.evaluate(lab, "TARI Training Lab", 1500.0).mode == "live_training"
    assert pol.evaluate(lab, "TARI Training Lab", 5000.0).mode == "restricted"  # stale beyond grace
    unknown = TextField(status="unknown")
    d = pol.evaluate(unknown, "VALORANT  ", 0.0)
    assert d.mode == "restricted" and not d.analysis_allowed and not d.spatial_overlays_allowed
    assert any("Riot authorization" in n for n in d.notices)
    assert pol.allows_analysis(EnvironmentObservation(kind="training_lab", confidence=0.95), unknown)
    assert not pol.allows_analysis(EnvironmentObservation(kind="unknown", confidence=0.0), unknown)


def test_authorized_verifier_path_exists_but_is_explicit():
    class Approved:
        def verify(self, label):
            return AuthorizationResult(True, "test-only approval")

    d = IntegrationPolicy(Approved()).evaluate(TextField(status="unknown"), "VALORANT", 0.0)
    assert d.mode == "live_authorized"
