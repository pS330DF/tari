"""Temporal state manager: fuses per-frame perception into a continuously
updated GameState and emits typed coaching events.

Values are labelled observed / estimated / stale / unknown. Hidden enemy
positions are never inferred; tracks that stop being observed coast briefly
(marked "coasting") and are then dropped.
"""

from __future__ import annotations

import math
from collections import deque

from tari_perception.geometry import Projection
from tari_perception.kb import load_environment_profile
from tari_schema import (
    BoolField, CoachingEvent, EnvironmentChangedEvent, EventSummary, GameState, IntField, MotionField,
    PerceptionNoticeEvent, PerceptionResult, Point2, PointField, ShotFiredEvent, SourceReconfiguredEvent, TextField,
    TextListField,
)

from .fields import CategoricalTracker
from .policy import IntegrationPolicy, PolicyDecision
from .shots import ShotDetector
from .tracker import FrameContext, TargetTracker, new_id

CAPTURE_GAP_MS = 1000.0
CROSSHAIR_MIN_CONF = 0.5
CROSSHAIR_NOTICE_FRAMES = 30


class TemporalStateManager:
    def __init__(self, session_id: str, policy: IntegrationPolicy | None = None, source_label: str = "",
                 hfov_deg: float = 103.0):
        self.session_id = session_id
        self.policy = policy or IntegrationPolicy()
        self.source_label = source_label
        self.hfov_deg = hfov_deg
        self.tracker = TargetTracker()
        self.shots = ShotDetector()
        self.environment = CategoricalTracker("environment", "fiducial", confirm_n=2)
        self.map = CategoricalTracker("map", "fiducial", confirm_n=2, ttl_ms=5000.0)
        self.drill = CategoricalTracker("drill", "hud", confirm_n=2, ttl_ms=5000.0)
        self.drill_names: dict[str, str] = dict(load_environment_profile().get("drills", {}))
        self.recent: deque[EventSummary] = deque(maxlen=12)
        self._dims: tuple[int, int] | None = None
        self._last_ts: float | None = None
        self._crosshair: tuple[float, float] | None = None
        self._gap_min: float | None = None
        self._gap_samples = 0
        self._effective_env = "unverified"
        self._module_states: dict[str, str] = {}
        self._crosshair_missing = 0
        self._crosshair_notice_sent = False
        self.decision: PolicyDecision | None = None
        self._last_snapshot: dict | None = None

    # -- configuration -------------------------------------------------------
    def configure(self, hfov_deg: float | None = None, source_label: str | None = None) -> None:
        if hfov_deg is not None:
            self.hfov_deg = hfov_deg
        if source_label is not None:
            self.source_label = source_label

    def _reset_temporal(self) -> None:
        self.tracker.reset()
        self.shots.reset()
        self._last_snapshot = None
        self._crosshair = None
        self._gap_min = None
        self._gap_samples = 0

    # -- main update -----------------------------------------------------------
    def update(self, p: PerceptionResult) -> tuple[GameState, list[CoachingEvent], PolicyDecision]:
        ts = p.acquired_ts_ms
        events: list[CoachingEvent] = []
        common = dict(session_id=self.session_id, frame_id=p.frame_id, ts_ms=ts)
        dims = (p.source_width, p.source_height)
        if dims != self._dims:
            reason = "session_start" if self._dims is None else "resolution_changed"
            self._reset_temporal()
            self._dims = dims
            events.append(SourceReconfiguredEvent(event_id=new_id(), confidence=1.0, reason=reason,
                                                  width=dims[0], height=dims[1], **common))
        elif self._last_ts is not None and ts - self._last_ts > CAPTURE_GAP_MS:
            gap = ts - self._last_ts
            self._reset_temporal()
            events.append(SourceReconfiguredEvent(event_id=new_id(), confidence=1.0, reason="capture_gap",
                                                  width=dims[0], height=dims[1], gap_ms=round(gap, 1), **common))
        dt = None if self._last_ts is None else ts - self._last_ts
        self._last_ts = ts
        proj = Projection(dims[0], dims[1], self.hfov_deg)

        # Environment & map (fiducial) with hysteresis.
        env = p.environment
        env_label = env.kind if (env is not None and env.kind != "unknown") else None
        self.environment.update(env_label, env.confidence if env else 0.0, ts)
        self.map.update(env.map_id if env is not None else None, env.confidence if env else 0.0, ts)
        env_field = self.environment.field(ts, "aruco fiducial")
        decision = self.policy.evaluate(env_field, self.source_label, ts)
        self.decision = decision
        effective = env_field.value if env_field.status == "observed" and env_field.value else "unverified"
        if effective != self._effective_env:
            events.append(EnvironmentChangedEvent(event_id=new_id(), confidence=round(env_field.confidence, 3),
                                                  previous=self._effective_env, current=effective,
                                                  coaching_mode=decision.mode, **common))
            self._effective_env = effective
            if effective != "training_lab":
                self._reset_temporal()

        # Crosshair.
        cross_field, crosshair_px, cross_conf = self._crosshair_field(p, ts)
        moving_field = self._movement_field(p, ts)

        # View motion.
        ego = p.ego_motion
        if ego is None:
            motion = MotionField(status="unknown", source="ego_motion",
                                 reason="needs two consecutive frames" if decision.analysis_allowed else "analysis restricted")
        elif not ego.measurable:
            motion = MotionField(status="unknown", source="ego_motion", method="phase correlation",
                                 reason="low texture or motion too fast to measure", updated_ts_ms=ts)
        else:
            motion = MotionField(status="observed", value=ego, confidence=ego.confidence, updated_ts_ms=ts,
                                 source="ego_motion", method="phase correlation")

        # HUD.
        ammo_field, timer_field, ammo_val, ammo_conf = self._hud_fields(p, ts)
        drill_raw = next((r for r in p.hud.readouts if r.name == "drill"), None) if p.hud else None
        if drill_raw is not None and drill_raw.value is not None:
            name = self.drill_names.get(str(drill_raw.value), f"drill_{drill_raw.value}")
            self.drill.update(name, drill_raw.confidence, ts)

        # Tracking and aim measurements.
        ctx = FrameContext(self.session_id, p.frame_id, ts, dt, proj, crosshair_px, cross_conf, ego)
        if decision.analysis_allowed:
            events.extend(self.tracker.update(p.targets, ctx))
        nearest = self.tracker.nearest_to_crosshair(ts) if decision.analysis_allowed else None
        speed = ctx.view_speed
        # A shot lands between the previous analyzed frame and this one; the HUD shows the
        # decrement in this frame, but this frame may already show the result (a hit target
        # flashes or disappears). The aim evidence for the shot is the pre-shot frame.
        pre_shot = self._last_snapshot
        snapshot = {
            "track_id": nearest[0].track_id if nearest else None,
            "error": nearest[1] if nearest else None,
            "on_head": nearest[0].on_head(nearest[1]) if nearest else None,
            "speed": speed,
            "moving": moving_field.value,
            "confidence": nearest[0].confidence * cross_conf if nearest else cross_conf,
        }
        self._last_snapshot = snapshot
        for shot in self.shots.update(ammo_val, ammo_conf, ts, p.frame_id, pre_shot or snapshot):
            err = shot.snapshot["error"]
            events.append(ShotFiredEvent(
                event_id=new_id(), session_id=self.session_id, frame_id=shot.frame_id, ts_ms=shot.ts_ms,
                confidence=round(min(1.0, ammo_conf * max(0.3, shot.snapshot["confidence"])), 3),
                shots=shot.shots, track_id=shot.snapshot["track_id"],
                error_deg=None if err is None else Point2(x=round(err[0], 3), y=round(err[1], 3)),
                on_head=shot.snapshot["on_head"],
                view_speed_dps=None if shot.snapshot["speed"] is None else round(shot.snapshot["speed"], 1),
                movement_error=shot.snapshot["moving"],
            ))

        events.extend(self._module_notices(p, ts, decision))
        for e in events:
            self.recent.append(EventSummary(event_id=e.event_id, type=e.type, ts_ms=e.ts_ms))

        confs = [c for c in (
            env.confidence if env and env.kind == "training_lab" else None,
            cross_conf if p.crosshair else None,
            min((r.confidence for r in p.hud.readouts), default=0.0) if p.hud else None,
            ego.confidence if ego else None,
        ) if c is not None]
        state = GameState(
            session_id=self.session_id, frame_id=p.frame_id, ts_ms=ts,
            environment=env_field,
            map=self.map.field(ts, "fiducial map id"),
            agent=TextField(status="unknown", reason="agent recognition not implemented"),
            abilities=TextListField(status="unknown", reason="ability recognition not implemented"),
            round_phase=TextField(status="unknown", reason="round-phase recognition not implemented"),
            drill=self.drill.field(ts, "hud drill readout"),
            teammates=TextListField(status="unknown", reason="teammate detection not implemented"),
            crosshair=cross_field, movement_error=moving_field, view_motion=motion,
            ammo=ammo_field, timer_s=timer_field,
            targets=self.tracker.states(ctx) if decision.analysis_allowed else [],
            recent_events=list(self.recent),
            observation_confidence=round(sum(confs) / len(confs), 3) if confs else 0.0,
            coaching_mode=decision.mode,  # type: ignore[arg-type]
            coaching_mode_reason=decision.reason,
        )
        return state, events, decision

    # -- field builders ------------------------------------------------------------
    def _crosshair_field(self, p: PerceptionResult, ts: float) -> tuple[PointField, tuple[float, float] | None, float]:
        c = p.crosshair
        if c is None:
            return PointField(status="unknown", source="crosshair", reason="crosshair analysis not run"), None, 0.0
        W, H = p.source_width, p.source_height
        if c.method == "detected" and c.confidence >= CROSSHAIR_MIN_CONF:
            x, y = c.position.x * W, c.position.y * H
            if self._crosshair is not None and math.hypot(x - self._crosshair[0], y - self._crosshair[1]) < 1.5:
                x = 0.5 * x + 0.5 * self._crosshair[0]
                y = 0.5 * y + 0.5 * self._crosshair[1]
            self._crosshair = (x, y)
            self._crosshair_missing = 0
            return (PointField(status="observed", value=Point2(x=x / W, y=y / H), confidence=c.confidence,
                               updated_ts_ms=ts, source="crosshair", method="color arm detection"),
                    (x, y), c.confidence)
        self._crosshair_missing += 1
        return (PointField(status="estimated", value=c.position, confidence=c.confidence, updated_ts_ms=ts,
                           source="crosshair", method="frame center assumed",
                           reason="crosshair not detected; check crosshair color setting"),
                None, c.confidence)

    def _movement_field(self, p: PerceptionResult, ts: float) -> BoolField:
        c = p.crosshair
        if c is None or c.method != "detected" or c.arm_gap_px is None:
            return BoolField(status="unknown", source="crosshair", reason="crosshair arm gap not measured")
        gap = c.arm_gap_px
        self._gap_samples += 1
        self._gap_min = gap if self._gap_min is None else min(self._gap_min, gap)
        if self._gap_samples < 5:
            return BoolField(status="unknown", source="crosshair", reason="calibrating resting crosshair gap")
        spread = gap - self._gap_min
        moving = spread >= max(1.5, 0.25 * self._gap_min)
        return BoolField(status="observed", value=moving, confidence=round(c.confidence, 3), updated_ts_ms=ts,
                         source="crosshair", method=f"movement-error spread {spread:.1f}px over resting gap")

    def _hud_fields(self, p: PerceptionResult, ts: float) -> tuple[IntField, IntField, int | None, float]:
        if p.hud is None:
            reason = "HUD not parsed (no fiducial anchor or analysis restricted)"
            return (IntField(status="unknown", source="hud", reason=reason),
                    IntField(status="unknown", source="hud", reason=reason), None, 0.0)
        fields: dict[str, IntField] = {}
        for r in p.hud.readouts:
            if r.value is None:
                fields[r.name] = IntField(status="unknown", source="hud", method=p.hud.profile,
                                          reason=f"readout unreadable ({r.raw or 'no contrast'})")
            else:
                fields[r.name] = IntField(status="observed", value=r.value, confidence=r.confidence,
                                          updated_ts_ms=ts, source="hud", method=p.hud.profile)
        ammo = fields.get("ammo", IntField(status="unknown", source="hud"))
        timer = fields.get("timer", IntField(status="unknown", source="hud"))
        return ammo, timer, ammo.value, ammo.confidence

    def _module_notices(self, p: PerceptionResult, ts: float, decision: PolicyDecision) -> list[CoachingEvent]:
        """One notice per module state transition, evaluated only while analysis is allowed."""
        out: list[CoachingEvent] = []
        if decision.analysis_allowed:
            for m in p.modules:
                if m.state == "skipped":
                    continue
                prev = self._module_states.get(m.name, "ok")
                if m.state == prev:
                    continue
                self._module_states[m.name] = m.state
                if m.state == "failed":
                    msg = f"{m.name} analysis failed: {m.detail or 'error'}. Its measurements are paused."
                elif m.name == "hud" and m.state in ("degraded", "unavailable"):
                    msg = "HUD not readable; shot timing analysis is paused until it is visible again."
                elif m.state == "ok" and prev in ("failed", "degraded", "unavailable"):
                    msg = f"{m.name} analysis recovered."
                else:
                    continue
                out.append(PerceptionNoticeEvent(event_id=new_id(), session_id=self.session_id, frame_id=p.frame_id,
                                                 ts_ms=ts, confidence=1.0, module=m.name, state=m.state, message=msg))
        if self._crosshair_missing >= CROSSHAIR_NOTICE_FRAMES and not self._crosshair_notice_sent and decision.analysis_allowed:
            self._crosshair_notice_sent = True
            out.append(PerceptionNoticeEvent(
                event_id=new_id(), session_id=self.session_id, frame_id=p.frame_id, ts_ms=ts, confidence=1.0,
                module="crosshair", state="degraded",
                message="Crosshair not detected. Aim measurements are paused; set your crosshair color in Settings.",
            ))
        elif self._crosshair_missing == 0:
            self._crosshair_notice_sent = False
        return out
