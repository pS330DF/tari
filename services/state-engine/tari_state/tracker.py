"""Target tracking and temporal aim measurements.

Measurements (all from pixels, timed by source-frame acquisition time):
- exposure: first frame a target's head is confidently localized, the
  silhouette has stopped widening (fully emerged from cover, so the head is
  not half-hidden) and the crosshair is detected; records the entry error
  (pre-aim placement). If emergence takes longer than 300 ms the exposure is
  recorded anyway with reduced confidence.
- acquisition: first frame the crosshair is on the head, i.e. within
  1.3 x the estimated head radius + 0.05 deg (small heads are only a few pixels
  across, so the tolerance absorbs radius/center quantization); acquisition
  time is measured from the target's first detection.
- flick analysis: error projected on the initial error direction; passing the
  head by more than its radius is an overshoot; stopping short and needing a
  second sub-movement is an undershoot. Sub-movements are segmented by view
  speed (phase correlation), falling back to error rate when unmeasurable.

Classifications like "overshoot" are *inferences* from measured error
trajectories and carry the measurement's confidence; they never claim intent.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

from tari_perception.geometry import Projection
from tari_schema import (
    CoachingEvent, EgoMotion, FlickAnalyzedEvent, Point2, Rect, TargetAcquiredEvent, TargetDetection,
    TargetExposedEvent, TargetLostEvent, TrackState,
)

SETTLED_DPS = 15.0
MOVING_DPS = 18.0
STOP_DPS = 8.0
EMERGED_GROWTH = 1.08  # silhouette width growing less than 8% per frame = fully out of cover
LOST_AFTER_MS = 250.0
LATE_EXPOSURE_MS = 300.0
FLICK_MIN_DEG = 1.0
FLICK_TIMEOUT_MS = 1500.0
SETTLE_AFTER_ACQ_MS = 120.0
CONFIDENT_METHODS = {"head_profile", "refined_crop"}
MIN_TRACK_CONFIDENCE = 0.45
RELIABLE_HEAD_CONFIDENCE = 0.7  # below this a head position is not used for timing/flick measurements


def new_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class FlickState:
    initial_mag: float
    direction: tuple[float, float]
    max_overshoot: float = 0.0
    past_frames: int = 0  # consecutive frames clearly beyond the head
    confirmed_overshoot: bool = False
    view_x: float = 0.0  # measured view rotation since exposure (deg, +right)
    view_y: float = 0.0  # (deg, +up)
    e0: tuple[float, float] = (0.0, 0.0)  # error at exposure
    unmeasured_frames: int = 0  # frames without measurable view motion
    first_stop_residual: float | None = None
    moving: bool = False
    submovements: int = 0
    acquired_ts: float | None = None
    done: bool = False


@dataclass
class Track:
    track_id: int
    first_seen_ts: float
    last_seen_ts: float
    head_px: tuple[float, float]
    radius_px: float
    bbox: Rect
    confidence: float
    method: str
    visible: bool = True
    exposure_emitted: bool = False
    exposure_ts: float | None = None
    entry_error: tuple[float, float] | None = None
    acquired: bool = False
    acquisition_ms: float | None = None
    flick: FlickState | None = None
    last_err: tuple[float, float] | None = None
    last_err_ts: float | None = None
    radius_deg: float | None = None
    history: list[tuple[float, float, float]] = field(default_factory=list)  # (ts, err_x, err_y)
    prev_width: float | None = None
    # Last error measured from a reliable head estimate, plus measured view motion since then.
    last_reliable_err: tuple[float, float] | None = None
    last_reliable_ts: float | None = None
    view_since_reliable: tuple[float, float] = (0.0, 0.0)

    def aim_error(self, now_ms: float, max_age_ms: float = 150.0, max_view_deg: float = 0.5) -> tuple[float, float] | None:
        """Best current aim error: the last reliable measurement, shifted by the view motion
        measured since (a target's own motion over <= 150 ms is ignored). None if too old."""
        if self.last_reliable_err is None or self.last_reliable_ts is None:
            return None
        if now_ms - self.last_reliable_ts > max_age_ms:
            return None
        vx, vy = self.view_since_reliable
        if math.hypot(vx, vy) > max_view_deg:
            return None
        return self.last_reliable_err[0] - vx, self.last_reliable_err[1] - vy

    def on_head(self, err: tuple[float, float]) -> bool | None:
        if self.radius_deg is None:
            return None
        return math.hypot(*err) <= ACQ_RADIUS_FACTOR * self.radius_deg + ACQ_MARGIN_DEG


@dataclass
class FrameContext:
    session_id: str
    frame_id: int
    ts_ms: float
    dt_ms: float | None
    projection: Projection
    crosshair_px: tuple[float, float] | None
    crosshair_confidence: float
    ego: EgoMotion | None

    @property
    def view_speed(self) -> float | None:
        if self.ego is None or not self.ego.measurable:
            return None
        return math.hypot(self.ego.view_rate_dps.x, self.ego.view_rate_dps.y)


ACQ_RADIUS_FACTOR = 1.3
ACQ_MARGIN_DEG = 0.05
OVERSHOOT_OUTSIDE_FACTOR = 1.5


class TargetTracker:
    def __init__(self, acquisition_tolerance: float = ACQ_RADIUS_FACTOR):
        self.tracks: dict[int, Track] = {}
        self._next_id = 1
        self.acquisition_tolerance = acquisition_tolerance

    def reset(self) -> None:
        self.tracks.clear()

    # -- main update -------------------------------------------------------
    def update(self, dets: list[TargetDetection], ctx: FrameContext) -> list[CoachingEvent]:
        events: list[CoachingEvent] = []
        W, H = ctx.projection.width, ctx.projection.height
        shift = (0.0, 0.0)
        if ctx.ego is not None and ctx.ego.measurable:
            shift = (ctx.ego.shift_px.x, ctx.ego.shift_px.y)

        if ctx.ego is not None and ctx.ego.measurable and ctx.dt_ms:
            dvx = ctx.ego.view_rate_dps.x * ctx.dt_ms / 1000.0
            dvy = ctx.ego.view_rate_dps.y * ctx.dt_ms / 1000.0
            for tr in self.tracks.values():
                tr.view_since_reliable = (tr.view_since_reliable[0] + dvx, tr.view_since_reliable[1] + dvy)

        det_px = [(d.head.x * W, d.head.y * H, d.head_radius * W) for d in dets]
        pairs: list[tuple[float, int, int]] = []
        for tid, tr in self.tracks.items():
            px, py = tr.head_px[0] + shift[0], tr.head_px[1] + shift[1]
            gate = max(4.0 * tr.radius_px, 0.05 * W)
            for j, (dx, dy, _r) in enumerate(det_px):
                dist = math.hypot(dx - px, dy - py)
                if dist <= gate:
                    pairs.append((dist, tid, j))
        pairs.sort()
        used_t: set[int] = set()
        used_d: set[int] = set()
        for _dist, tid, j in pairs:
            if tid in used_t or j in used_d:
                continue
            used_t.add(tid)
            used_d.add(j)
            self._observe(self.tracks[tid], dets[j], det_px[j], ctx, events)

        # Fast flicks can make view motion unmeasurable, so a target's apparent jump cannot be
        # compensated. Re-associate only when unambiguous: exactly one track seen last frame and
        # exactly one new detection of similar size; otherwise prefer a new track.
        if ctx.ego is None or not ctx.ego.measurable:
            open_t = [tid for tid, tr in self.tracks.items()
                      if tid not in used_t and tr.visible and ctx.dt_ms is not None
                      and ctx.ts_ms - tr.last_seen_ts <= ctx.dt_ms * 1.5]
            open_d = [j for j in range(len(dets)) if j not in used_d and dets[j].confidence >= MIN_TRACK_CONFIDENCE]
            if len(open_t) == 1 and len(open_d) == 1:
                tr, j = self.tracks[open_t[0]], open_d[0]
                ratio = det_px[j][2] / max(tr.radius_px, 1e-6)
                if 0.65 <= ratio <= 1.55:
                    used_t.add(tr.track_id)
                    used_d.add(j)
                    self._observe(tr, dets[j], det_px[j], ctx, events)

        for j, det in enumerate(dets):
            if j in used_d or det.confidence < MIN_TRACK_CONFIDENCE:
                continue
            tr = Track(self._next_id, ctx.ts_ms, ctx.ts_ms, (det_px[j][0], det_px[j][1]), det_px[j][2],
                       det.bbox, det.confidence, det.head_method)
            self._next_id += 1
            self.tracks[tr.track_id] = tr
            self._observe(tr, det, det_px[j], ctx, events, new=True)

        for tid in list(self.tracks):
            if tid in used_t:
                continue
            tr = self.tracks[tid]
            if tr.first_seen_ts == ctx.ts_ms:
                continue
            tr.visible = False
            tr.head_px = (tr.head_px[0] + shift[0], tr.head_px[1] + shift[1])
            if ctx.ts_ms - tr.last_seen_ts > LOST_AFTER_MS:
                if tr.flick is not None and not tr.flick.done:
                    events.append(self._finalize_flick(tr, ctx))
                if tr.exposure_emitted:
                    events.append(TargetLostEvent(
                        event_id=new_id(), session_id=ctx.session_id, frame_id=ctx.frame_id, ts_ms=ctx.ts_ms,
                        confidence=round(tr.confidence, 3), track_id=tr.track_id,
                        visible_ms=round(tr.last_seen_ts - tr.first_seen_ts, 1), acquired=tr.acquired,
                    ))
                del self.tracks[tid]
        return events

    def _observe(self, tr: Track, det: TargetDetection, px: tuple[float, float, float], ctx: FrameContext,
                 events: list[CoachingEvent], new: bool = False) -> None:
        width = det.bbox.w
        emerged = tr.prev_width is not None and width <= tr.prev_width * EMERGED_GROWTH
        tr.prev_width = width
        tr.head_px = (px[0], px[1])
        tr.radius_px = px[2]
        tr.bbox = det.bbox
        tr.confidence = det.confidence
        tr.method = det.head_method
        tr.last_seen_ts = ctx.ts_ms
        tr.visible = True
        if ctx.crosshair_px is None:
            tr.last_err = None
            return
        err = ctx.projection.angular_offset(ctx.crosshair_px, tr.head_px)
        radius_deg = ctx.projection.length_deg(tr.radius_px)
        tr.radius_deg = radius_deg
        prev_err, prev_ts = tr.last_err, tr.last_err_ts
        tr.last_err, tr.last_err_ts = err, ctx.ts_ms
        tr.history.append((ctx.ts_ms, err[0], err[1]))
        if len(tr.history) > 90:
            del tr.history[:30]
        mag = math.hypot(err[0], err[1])
        speed = ctx.view_speed

        confident_head = det.head_method in CONFIDENT_METHODS or det.confidence >= 0.75
        late = ctx.ts_ms - tr.first_seen_ts > LATE_EXPOSURE_MS
        if not tr.exposure_emitted and confident_head and (emerged or late):
            conf = det.confidence * ctx.crosshair_confidence * (0.6 if late else 1.0)
            tr.exposure_emitted = True
            tr.exposure_ts = ctx.ts_ms
            tr.entry_error = err
            events.append(TargetExposedEvent(
                event_id=new_id(), session_id=ctx.session_id, frame_id=ctx.frame_id, ts_ms=ctx.ts_ms,
                confidence=round(min(1.0, conf), 3), track_id=tr.track_id,
                head=Point2(x=tr.head_px[0] / ctx.projection.width, y=tr.head_px[1] / ctx.projection.height),
                entry_error_deg=Point2(x=round(err[0], 3), y=round(err[1], 3)),
                head_radius_deg=round(radius_deg, 3),
                view_speed_dps=None if speed is None else round(speed, 1),
                view_settled=None if speed is None else speed < SETTLED_DPS,
            ))
            if mag > max(2.5 * radius_deg, FLICK_MIN_DEG):
                tr.flick = FlickState(initial_mag=mag, direction=(err[0] / mag, err[1] / mag), e0=err)

        # A crosshair covering a small head hides it; such frames give fallback (unreliable)
        # head estimates, which must not drive acquisition or flick classification.
        reliable = det.head_method in CONFIDENT_METHODS and det.confidence >= RELIABLE_HEAD_CONFIDENCE
        if reliable:
            tr.last_reliable_err, tr.last_reliable_ts, tr.view_since_reliable = err, ctx.ts_ms, (0.0, 0.0)
        if (reliable and tr.exposure_emitted and not tr.acquired
                and mag <= radius_deg * self.acquisition_tolerance + ACQ_MARGIN_DEG):
            tr.acquired = True
            tr.acquisition_ms = ctx.ts_ms - tr.first_seen_ts
            events.append(TargetAcquiredEvent(
                event_id=new_id(), session_id=ctx.session_id, frame_id=ctx.frame_id, ts_ms=ctx.ts_ms,
                confidence=round(min(1.0, det.confidence * ctx.crosshair_confidence), 3), track_id=tr.track_id,
                acquisition_ms=round(tr.acquisition_ms, 1),
                resolution_ms=round(ctx.dt_ms if ctx.dt_ms is not None else 0.0, 1),
                entry_error_deg=Point2(x=round(tr.entry_error[0], 3), y=round(tr.entry_error[1], 3))
                if tr.entry_error else Point2(x=err[0], y=err[1]),
            ))
            if tr.flick is not None:
                tr.flick.acquired_ts = ctx.ts_ms

        fl = tr.flick
        if fl is not None and not fl.done and not new:
            if ctx.ego is not None and ctx.ego.measurable and ctx.dt_ms:
                fl.view_x += ctx.ego.view_rate_dps.x * ctx.dt_ms / 1000.0
                fl.view_y += ctx.ego.view_rate_dps.y * ctx.dt_ms / 1000.0
            elif prev_err is not None and reliable:
                # Unmeasurable view motion (typically a very fast flick): infer this frame's view
                # step from the error change, assuming the target held still for one frame. The
                # count is reported on the event, and undershoot compensation is disabled.
                fl.view_x -= err[0] - prev_err[0]
                fl.view_y -= err[1] - prev_err[1]
                fl.unmeasured_frames += 1
            else:
                fl.unmeasured_frames += 1
            vmag = math.hypot(fl.view_x, fl.view_y)
            threshold = max(radius_deg, 0.35)
            moved_toward = (vmag >= max(1.0, 0.5 * fl.initial_mag)
                            and (fl.view_x * fl.direction[0] + fl.view_y * fl.direction[1]) / vmag > 0.5)
            u = (fl.view_x / vmag, fl.view_y / vmag) if moved_toward else fl.direction
            along = err[0] * u[0] + err[1] * u[1]
            if reliable and moved_toward:
                past = -along
                # The crosshair partly covers the head: its estimate is less certain, so demand more.
                margin = threshold + max(0.5 * radius_deg, 0.2) if det.crosshair_overlap else threshold
                if past > margin and mag > OVERSHOOT_OUTSIDE_FACTOR * radius_deg:
                    fl.past_frames += 1
                    fl.max_overshoot = max(fl.max_overshoot, past)
                    if fl.past_frames >= 2:
                        fl.confirmed_overshoot = True
                else:
                    fl.past_frames = 0
            if speed is None and prev_err is not None and prev_ts is not None and ctx.ts_ms > prev_ts:
                speed = math.hypot(err[0] - prev_err[0], err[1] - prev_err[1]) * 1000.0 / (ctx.ts_ms - prev_ts)
            if speed is not None:
                if not fl.moving and speed > MOVING_DPS:
                    fl.moving = True
                    fl.submovements += 1
                elif fl.moving and speed < STOP_DPS:
                    fl.moving = False
                    if fl.first_stop_residual is None and reliable and fl.unmeasured_frames == 0:
                        # Where the crosshair stopped relative to where the target *was*:
                        # err = e0 + T - V, so removing the target's motion T leaves e0 - V.
                        fl.first_stop_residual = ((fl.e0[0] - fl.view_x) * u[0] + (fl.e0[1] - fl.view_y) * u[1])
            settled_after_acq = (fl.acquired_ts is not None and not fl.moving
                                 and ctx.ts_ms - fl.acquired_ts >= SETTLE_AFTER_ACQ_MS)
            timed_out = tr.exposure_ts is not None and ctx.ts_ms - tr.exposure_ts > FLICK_TIMEOUT_MS
            if settled_after_acq or timed_out:
                events.append(self._finalize_flick(tr, ctx))

    def _finalize_flick(self, tr: Track, ctx: FrameContext) -> FlickAnalyzedEvent:
        fl = tr.flick
        assert fl is not None
        fl.done = True
        r = tr.radius_deg or 0.3
        threshold = max(r, 0.35)
        if fl.confirmed_overshoot:
            outcome = "overshoot"
        elif fl.first_stop_residual is not None and fl.first_stop_residual > threshold and fl.submovements >= 2:
            outcome = "undershoot"
        elif tr.acquired:
            outcome = "clean"
        else:
            outcome = "unresolved"
        return FlickAnalyzedEvent(
            event_id=new_id(), session_id=ctx.session_id, frame_id=ctx.frame_id, ts_ms=ctx.ts_ms,
            confidence=round(min(1.0, tr.confidence * ctx.crosshair_confidence), 3), track_id=tr.track_id,
            outcome=outcome,  # type: ignore[arg-type]
            initial_error_deg=round(fl.initial_mag, 3),
            overshoot_deg=round(fl.max_overshoot, 3) if fl.max_overshoot > 0 else None,
            residual_deg=None if fl.first_stop_residual is None else round(fl.first_stop_residual, 3),
            submovements=fl.submovements,
            inferred_view_frames=fl.unmeasured_frames,
        )

    # -- queries -------------------------------------------------------------
    def nearest_to_crosshair(self, now_ms: float) -> tuple[Track, tuple[float, float]] | None:
        """Track whose (reliable) aim error is smallest, with that error."""
        best: tuple[Track, tuple[float, float]] | None = None
        best_mag = float("inf")
        for tr in self.tracks.values():
            err = tr.aim_error(now_ms)
            if err is None:
                continue
            mag = math.hypot(*err)
            if mag < best_mag:
                best, best_mag = (tr, err), mag
        return best

    def states(self, ctx: FrameContext) -> list[TrackState]:
        W, H = ctx.projection.width, ctx.projection.height
        out = []
        for tr in self.tracks.values():
            out.append(TrackState(
                track_id=tr.track_id, status="visible" if tr.visible else "coasting",
                head=Point2(x=tr.head_px[0] / W, y=tr.head_px[1] / H), head_radius=tr.radius_px / W,
                bbox=tr.bbox, confidence=round(tr.confidence, 3), first_seen_ts_ms=tr.first_seen_ts,
                last_seen_ts_ms=tr.last_seen_ts,
                error_deg=Point2(x=round(tr.last_err[0], 3), y=round(tr.last_err[1], 3))
                if (tr.last_err is not None and tr.visible) else None,
                head_radius_deg=None if tr.radius_deg is None else round(tr.radius_deg, 3),
                acquired=tr.acquired,
                acquisition_ms=None if tr.acquisition_ms is None else round(tr.acquisition_ms, 1),
            ))
        return out
