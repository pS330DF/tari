import pytest

from helpers import run_scenario
from tari_coaching import PriorityConfidenceFilter
from tari_coaching.voice import VoiceBuilder
from tari_schema import CoachingRecommendation, CoachingSettings, Evidence, Expiration
from tari_synth import angle_hold, flicks


@pytest.fixture(scope="module")
def low_placement():
    return run_scenario(angle_hold(n=6, entry=(1.0, 1.5), seed=4))


def test_low_placement_produces_evidence_backed_recommendation(low_placement):
    recs = [r for r in low_placement.recs if r.rule_id == "aim.placement.low"]
    assert len(recs) == 1  # duplicates suppressed by the filter cooldown
    r = recs[0]
    assert r.domain == "aim" and r.priority == "P1" and r.tone == "corrective"
    ev = r.evidence[0]
    assert ev.metric == "vertical_entry_offset_deg"
    assert ev.value == pytest.approx(1.5, abs=0.3)
    assert ev.samples >= 4 and "crosshair" in ev.method
    assert f"{ev.value:.1f}°" in r.observation  # the number shown is the measured number
    assert "head" in r.observation and "head" in r.suggestion.lower()
    assert r.expiration.expires_ts_ms > r.created_ts_ms and r.expiration.until_event == "target_exposed"
    assert "%" not in r.observation  # no unsupported percentages


def test_no_recommendation_before_minimum_samples():
    run = run_scenario(angle_hold(n=3, entry=(1.0, 1.5), seed=4))
    assert not [r for r in run.recs if r.rule_id.startswith("aim.placement")]


def test_good_placement_does_not_trigger_correction():
    run = run_scenario(angle_hold(n=5, entry=(0.8, 0.1), jitter=0.15, seed=6))
    assert not [r for r in run.recs if r.rule_id in ("aim.placement.low", "aim.placement.high")]


def test_overshoot_rule_fires_on_overshoot_flicks():
    run = run_scenario(flicks(n=6, outcome="overshoot", seed=2))
    rules = {r.rule_id for r in run.recs}
    assert "aim.flick.overshoot" in rules
    assert not any(r.startswith("aim.placement") for r in rules)  # flick drill read from HUD: no placement rules
    assert run.states[-1].drill.value == "flick"
    clean = run_scenario(flicks(n=6, outcome="clean", seed=2))
    assert "aim.flick.overshoot" not in {r.rule_id for r in clean.recs}


def test_moving_shots_rule():
    run = run_scenario(angle_hold(n=6, entry=(0.8, 0.2), moving_at_shot=True, seed=8))
    assert "aim.shot.moving" in {r.rule_id for r in run.recs}


def test_korean_language_output():
    run = run_scenario(angle_hold(n=6, entry=(1.0, 1.5), seed=4), coaching=CoachingSettings(language="ko"))
    r = next(r for r in run.recs if r.rule_id == "aim.placement.low")
    assert r.language == "ko" and "머리" in r.observation
    flashes = [p.text for o in run.overlays for p in o.primitives if p.kind == "text" and p.text]
    assert any("낮음" in t for t in flashes)


def test_overlays_are_bound_to_source_frames(low_placement):
    frame_ts = {p.frame_id: p.acquired_ts_ms for p in low_placement.perceptions}
    assert low_placement.overlays
    for o in low_placement.overlays:
        assert o.source_ts_ms == frame_ts[o.source_frame_id]
        assert 0 < o.ttl_ms <= 500 and o.gated_by == "training_lab"
    kinds = {p.kind for o in low_placement.overlays for p in o.primitives}
    assert {"cross", "circle", "box", "hline", "arrow"} <= kinds


def test_density_minimal_reduces_primitives():
    std = run_scenario(angle_hold(n=2, entry=(1.0, 1.5), seed=4))
    mini = run_scenario(angle_hold(n=2, entry=(1.0, 1.5), seed=4), coaching=CoachingSettings(overlay_density="minimal"))
    assert sum(len(o.primitives) for o in mini.overlays) < sum(len(o.primitives) for o in std.overlays)
    assert not any(p.kind == "box" for o in mini.overlays for p in o.primitives)


# -- filter / voice unit tests ------------------------------------------------------------

def rec(rule="aim.placement.low", conf=0.8, priority="P1", ts=0.0, domain="aim"):
    return CoachingRecommendation(
        rec_id=f"{rule}-{ts}", session_id="s", created_ts_ms=ts, source_frame_id=1, source_ts_ms=ts,
        domain=domain, rule_id=rule, dedupe_key=rule, priority=priority, confidence=conf, tone="corrective",
        observation="o", suggestion="s", reasoning="r", short_text="short",
        evidence=[Evidence(metric="m", value=1.0, unit="deg", samples=5, method="test")],
        expiration=Expiration(ttl_ms=1000, expires_ts_ms=ts + 1000), language="en",
    )


def test_filter_rejects_low_confidence_and_duplicates():
    f = PriorityConfidenceFilter(CoachingSettings(min_confidence=0.6, intensity="balanced"))
    assert f.apply([rec(conf=0.5)], 0.0) == []
    assert f.stats.low_confidence == 1
    assert len(f.apply([rec(conf=0.9)], 0.0)) == 1
    assert f.apply([rec(conf=0.9, ts=10_000)], 10_000) == []  # same key inside 30 s cooldown
    assert f.stats.duplicate == 1
    assert len(f.apply([rec(conf=0.9, ts=31_000)], 31_000)) == 1


def test_filter_rate_limits_but_lets_p0_through():
    f = PriorityConfidenceFilter(CoachingSettings(intensity="balanced"))
    out = f.apply([rec("a"), rec("b"), rec("sys", priority="P0", domain="system")], 0.0)
    assert [r.rule_id for r in out] == ["sys", "a"]
    assert f.stats.rate_limited == 1


def test_filter_respects_focus():
    f = PriorityConfidenceFilter(CoachingSettings(focus=["positioning"]))
    assert f.apply([rec()], 0.0) == [] and f.stats.out_of_focus == 1


@pytest.mark.parametrize("freq,expected", [("off", 0), ("minimal", 1), ("normal", 2), ("frequent", 3)])
def test_voice_frequency_caps_priorities(freq, expected):
    vb = VoiceBuilder("s", CoachingSettings(voice_frequency=freq))
    out = vb.from_recommendations([rec("a", priority="P1"), rec("b", priority="P2"), rec("c", priority="P3")])
    assert len(out) == expected
    assert all(v.ttl_ms > 0 and not v.interrupt for v in out)


def test_restricted_mode_announces_pause_with_p0_voice():
    from tari_coaching import CoachingOrchestrator
    from tari_schema import GameState, TextField
    from tari_state import PolicyDecision

    from tari_schema import BoolField, IntField, MotionField, PointField, TextListField

    orch = CoachingOrchestrator("s", CoachingSettings())
    live = PolicyDecision("live_training", "lab", True, True, True)
    paused = PolicyDecision("restricted", "no", False, False, False)
    state = GameState(session_id="s", frame_id=0, ts_ms=0.0, environment=TextField(), map=TextField(),
                      agent=TextField(), abilities=TextListField(), round_phase=TextField(), teammates=TextListField(),
                      crosshair=PointField(), movement_error=BoolField(), view_motion=MotionField(), ammo=IntField(),
                      timer_s=IntField(), observation_confidence=0.0, coaching_mode="restricted",
                      coaching_mode_reason="test")
    out1 = orch.process(state, [], live, (1920, 1080), {}, 0.0)
    assert [v.priority for v in out1.voice] == ["P2"] and len(out1.overlays) == 1
    out2 = orch.process(state, [], paused, (1920, 1080), {}, 0.0)
    assert [v.priority for v in out2.voice] == ["P0"] and out2.voice[0].interrupt
    assert out2.recommendations == [] and out2.overlays == []
