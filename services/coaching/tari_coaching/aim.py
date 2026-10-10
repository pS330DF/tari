"""Aim coach: deterministic rules over streaming aim measurements.

Every recommendation is computed from events of the current session window
and carries the metric value, sample count and the calculation method. The
coach never reports accuracy percentages; it reports counts of measured
events (e.g. "4 of your last 6 shots...") with the method behind them.
"""

from __future__ import annotations

import statistics
import uuid
from collections import deque
from dataclasses import dataclass

from tari_schema import (
    CoachingEvent, CoachingRecommendation, CoachingSettings, Evidence, Expiration, GameState,
)

from .phrasing import Phraser

THRESHOLDS = {
    "lenient": dict(vert=1.4, horiz=6.0, acq=620.0, overshoot=0.5, undershoot=0.5, unstable=0.5, moving=0.5),
    "balanced": dict(vert=0.9, horiz=4.0, acq=480.0, overshoot=0.4, undershoot=0.4, unstable=0.35, moving=0.35),
    "strict": dict(vert=0.6, horiz=2.5, acq=380.0, overshoot=0.3, undershoot=0.3, unstable=0.25, moving=0.25),
}
SKILL_ACQ_ADJUST = {"new": 150.0, "intermediate": 0.0, "advanced": -60.0}
MIN_SAMPLES = {"placement": 4, "acquisition": 5, "flicks": 5, "shots": 5}
WINDOW = 8
UNSTABLE_DPS = 40.0
MIN_SAMPLE_CONFIDENCE = 0.4

METHOD_PLACEMENT = ("At each target's first fully-visible frame, the vertical angle between the detected crosshair "
                    "center and the estimated head center (pinhole projection, horizontal FOV from settings). "
                    "Only exposures where measured view speed was under 15°/s (angle held) are included.")
METHOD_HORIZONTAL = "Same exposures as placement; absolute horizontal angle from crosshair to head center."
METHOD_ACQUISITION = ("Time from a target's first detection to the first analyzed frame with the crosshair inside the "
                      "estimated head radius. Resolution is one analyzed-frame interval.")
METHOD_FLICK = ("Error projected on the initial crosshair-to-head direction. Overshoot: crosshair passed the head "
                "center by more than the head radius. Undershoot: first movement stopped with more than a head radius "
                "left and a second movement followed. Movement segmentation uses phase-correlation view speed.")
METHOD_SHOTS = ("Shots detected from HUD ammo decrements (confirmed on the next frame). View speed from phase "
                "correlation at the shot frame; movement from crosshair movement-error spread.")


@dataclass
class FeedbackFlash:
    track_id: int
    text: str
    style: str
    until_ts: float


@dataclass
class _Exposure:
    ts: float
    ex: float
    ey: float
    settled: bool
    conf: float


class _Window:
    """Rolling (bounded) or whole-session (maxlen=None) measurement buffers."""

    def __init__(self, maxlen: int | None):
        self.exposures: deque[_Exposure] = deque(maxlen=maxlen)
        self.acquisitions: deque[tuple] = deque(maxlen=maxlen)
        self.flicks: deque[tuple] = deque(maxlen=maxlen)
        self.shots: deque[tuple] = deque(maxlen=maxlen)


def _sample_factor(n: int) -> float:
    return min(1.0, 0.6 + 0.05 * n)


class AimCoach:
    domain = "aim"

    def __init__(self, session_id: str, settings: CoachingSettings):
        self.session_id = session_id
        self.window = _Window(16)
        self.totals = _Window(None)
        self.flashes: dict[int, FeedbackFlash] = {}
        self.flagged: set[str] = set()
        self.configure(settings)

    def configure(self, settings: CoachingSettings) -> None:
        self.settings = settings
        self.phraser = Phraser(settings.language)
        self.t = dict(THRESHOLDS[settings.strictness])
        self.t["acq"] += SKILL_ACQ_ADJUST[settings.skill_level]

    # -- streaming input ------------------------------------------------------
    def observe(self, events: list[CoachingEvent], state: GameState, now_ts: float) -> list[CoachingRecommendation]:
        kinds: set[str] = set()
        for e in events:
            if e.type == "target_exposed":
                if e.confidence < MIN_SAMPLE_CONFIDENCE:
                    continue
                x = _Exposure(e.ts_ms, e.entry_error_deg.x, e.entry_error_deg.y, bool(e.view_settled), e.confidence)
                self.window.exposures.append(x)
                self.totals.exposures.append(x)
                self._flash_exposure(e.track_id, e.entry_error_deg.y, e.head_radius_deg, e.ts_ms)
                kinds.add(e.type)
            elif e.type == "target_acquired" and e.confidence >= MIN_SAMPLE_CONFIDENCE:
                item = (e.ts_ms, e.acquisition_ms, e.resolution_ms, e.confidence)
                self.window.acquisitions.append(item)
                self.totals.acquisitions.append(item)
                self.flashes[e.track_id] = FeedbackFlash(e.track_id, self.phraser.flash("acquired", v=e.acquisition_ms),
                                                         "label", e.ts_ms + 900.0)
                kinds.add(e.type)
            elif e.type == "flick_analyzed" and e.outcome != "unresolved" and e.confidence >= MIN_SAMPLE_CONFIDENCE:
                item = (e.ts_ms, e.outcome, e.overshoot_deg, e.residual_deg, e.submovements, e.confidence)
                self.window.flicks.append(item)
                self.totals.flicks.append(item)
                kinds.add(e.type)
            elif e.type == "shot_fired":
                item = (e.ts_ms, e.view_speed_dps, e.movement_error, e.on_head, e.confidence)
                self.window.shots.append(item)
                self.totals.shots.append(item)
                kinds.add(e.type)
        self.flashes = {k: v for k, v in self.flashes.items() if v.until_ts >= now_ts}

        recs: list[CoachingRecommendation] = []
        # Placement rules judge pre-aim while holding an angle; in the flick drill wide
        # entries are the point of the exercise, so those rules stay quiet there.
        drill = state.drill.value if state.drill.status == "observed" else None
        if "target_exposed" in kinds and drill != "flick":
            recs += self._rule_placement(state)
        if "target_acquired" in kinds:
            recs += self._rule_acquisition(state)
        if "flick_analyzed" in kinds:
            recs += self._rule_flicks(state)
        if "shot_fired" in kinds:
            recs += self._rule_shots(state)
        return recs

    def _flash_exposure(self, track_id: int, ey: float, radius_deg: float, ts: float) -> None:
        tol = max(0.5 * self.t["vert"], radius_deg)
        if abs(ey) <= tol:
            text, style = self.phraser.flash("level"), "good"
        elif ey > 0:
            text, style = self.phraser.flash("low", v=ey), "warning"
        else:
            text, style = self.phraser.flash("high", v=-ey), "warning"
        self.flashes[track_id] = FeedbackFlash(track_id, text, style, ts + 900.0)

    # -- rules -----------------------------------------------------------------
    def _rule_placement(self, state: GameState) -> list[CoachingRecommendation]:
        settled = [x for x in self.window.exposures if x.settled][-WINDOW:]
        n = len(settled)
        if n < MIN_SAMPLES["placement"]:
            return []
        conf = statistics.fmean(x.conf for x in settled) * _sample_factor(n)
        ys = [x.ey for x in settled]
        med = statistics.median(ys)
        thr = self.t["vert"]
        recs: list[CoachingRecommendation] = []
        low_k = sum(1 for y in ys if y > 0.5 * thr)
        high_k = sum(1 for y in ys if y < -0.5 * thr)
        ev = [Evidence(metric="vertical_entry_offset_deg", value=round(med, 2), unit="deg", samples=n,
                       method=METHOD_PLACEMENT, detail=f"positive = crosshair below head; threshold {thr:.1f}°")]
        if med > thr and low_k / n >= 0.6:
            self.flagged.add("placement")
            recs.append(self._make("aim.placement.low", "P1", "corrective", conf, ev, state,
                                   self.phraser.render("aim.placement.low", med=med, k=low_k, n=n),
                                   until_event="target_exposed"))
        elif med < -thr and high_k / n >= 0.6:
            self.flagged.add("placement")
            recs.append(self._make("aim.placement.high", "P1", "corrective", conf, ev, state,
                                   self.phraser.render("aim.placement.high", med=-med, k=high_k, n=n),
                                   until_event="target_exposed"))
        elif "placement" in self.flagged and abs(med) <= thr * 0.75:
            self.flagged.discard("placement")
            recs.append(self._make("aim.placement.good", "P3", "reinforcing", conf, ev, state,
                                   self.phraser.render("aim.placement.good", med=abs(med), n=n)))

        xs = [x.ex for x in settled]
        hmed = statistics.median(abs(x) for x in xs)
        if hmed > self.t["horiz"]:
            right = sum(1 for x in xs if x > 0)
            side = "right" if right >= n / 2 else "left"
            consistent = max(right, n - right) / n >= 0.75
            dir_text = self.phraser.flash(side) if consistent else ("" if self.phraser.language == "ko" else "away")
            hev = [Evidence(metric="horizontal_entry_offset_deg", value=round(hmed, 2), unit="deg", samples=n,
                            method=METHOD_HORIZONTAL, detail=f"threshold {self.t['horiz']:.1f}°")]
            recs.append(self._make("aim.placement.wide", "P2", "corrective", conf * 0.9, hev, state,
                                   self.phraser.render("aim.placement.wide", med=hmed, n=n, dir=dir_text)))
        return recs

    def _rule_acquisition(self, state: GameState) -> list[CoachingRecommendation]:
        acq = list(self.window.acquisitions)[-WINDOW:]
        n = len(acq)
        if n < MIN_SAMPLES["acquisition"]:
            return []
        med = statistics.median(a[1] for a in acq)
        res = statistics.median(a[2] for a in acq)
        if med <= self.t["acq"]:
            return []
        conf = statistics.fmean(a[3] for a in acq) * _sample_factor(n)
        ev = [Evidence(metric="acquisition_time_ms", value=round(med, 0), unit="ms", samples=n,
                       method=METHOD_ACQUISITION, detail=f"±{res:.0f} ms resolution; threshold {self.t['acq']:.0f} ms")]
        return [self._make("aim.acquisition.slow", "P2", "corrective", conf, ev, state,
                           self.phraser.render("aim.acquisition.slow", med=med, n=n, thr=self.t["acq"]))]

    def _rule_flicks(self, state: GameState) -> list[CoachingRecommendation]:
        fl = list(self.window.flicks)[-WINDOW:]
        n = len(fl)
        if n < MIN_SAMPLES["flicks"]:
            return []
        conf = statistics.fmean(f[5] for f in fl) * _sample_factor(n)
        over = [f for f in fl if f[1] == "overshoot"]
        under = [f for f in fl if f[1] == "undershoot"]
        recs = []
        if len(over) / n >= self.t["overshoot"]:
            med = statistics.median(f[2] or 0.0 for f in over)
            ev = [Evidence(metric="overshoot_deg", value=round(med, 2), unit="deg", samples=n, method=METHOD_FLICK,
                           detail=f"{len(over)} of {n} flicks classified overshoot")]
            recs.append(self._make("aim.flick.overshoot", "P1", "corrective", conf, ev, state,
                                   self.phraser.render("aim.flick.overshoot", k=len(over), n=n, med=med)))
        elif len(under) / n >= self.t["undershoot"]:
            med = statistics.median(f[3] or 0.0 for f in under)
            ev = [Evidence(metric="first_stop_residual_deg", value=round(med, 2), unit="deg", samples=n,
                           method=METHOD_FLICK, detail=f"{len(under)} of {n} flicks classified undershoot")]
            recs.append(self._make("aim.flick.undershoot", "P1", "corrective", conf, ev, state,
                                   self.phraser.render("aim.flick.undershoot", k=len(under), n=n, med=med)))
        return recs

    def _rule_shots(self, state: GameState) -> list[CoachingRecommendation]:
        shots = list(self.window.shots)[-WINDOW:]
        recs = []
        timed = [s for s in shots if s[1] is not None]
        if len(timed) >= MIN_SAMPLES["shots"]:
            k = sum(1 for s in timed if s[1] > UNSTABLE_DPS)
            if k / len(timed) >= self.t["unstable"]:
                conf = statistics.fmean(s[4] for s in timed) * _sample_factor(len(timed))
                ev = [Evidence(metric="shots_fired_while_moving_view", value=float(k), unit="shots",
                               samples=len(timed), method=METHOD_SHOTS, detail=f"view speed > {UNSTABLE_DPS:.0f}°/s")]
                recs.append(self._make("aim.shot.unstable", "P1", "corrective", conf, ev, state,
                                       self.phraser.render("aim.shot.unstable", k=k, n=len(timed), thr=UNSTABLE_DPS)))
        observed = [s for s in shots if s[2] is not None]
        if len(observed) >= MIN_SAMPLES["shots"]:
            k = sum(1 for s in observed if s[2])
            if k / len(observed) >= self.t["moving"]:
                conf = statistics.fmean(s[4] for s in observed) * _sample_factor(len(observed))
                ev = [Evidence(metric="shots_fired_while_moving", value=float(k), unit="shots",
                               samples=len(observed), method=METHOD_SHOTS)]
                recs.append(self._make("aim.shot.moving", "P1", "corrective", conf, ev, state,
                                       self.phraser.render("aim.shot.moving", k=k, n=len(observed))))
        return recs

    # -- helpers -----------------------------------------------------------------
    def _make(self, rule_id: str, priority: str, tone: str, conf: float, evidence: list[Evidence], state: GameState,
              text: dict[str, str], until_event: str | None = None, ttl_ms: float = 15000.0) -> CoachingRecommendation:
        return CoachingRecommendation(
            rec_id=uuid.uuid4().hex[:16], session_id=self.session_id, created_ts_ms=state.ts_ms,
            source_frame_id=state.frame_id, source_ts_ms=state.ts_ms, domain="aim", rule_id=rule_id,
            dedupe_key=rule_id, priority=priority,  # type: ignore[arg-type]
            confidence=round(max(0.0, min(1.0, conf)), 3), tone=tone,  # type: ignore[arg-type]
            observation=text["observation"], suggestion=text["suggestion"], reasoning=text["reasoning"],
            short_text=text["short"], evidence=evidence,
            context={
                "environment": state.environment.value or "unknown",
                "drill": state.drill.value or "unknown",
                "map": state.map.value or "unknown",
                "agent": state.agent.value or "unknown",
                "strictness": self.settings.strictness,
            },
            expiration=Expiration(ttl_ms=ttl_ms, expires_ts_ms=state.ts_ms + ttl_ms, until_event=until_event),
            language=self.settings.language,
        )

    # -- session summary ----------------------------------------------------------
    def summary(self) -> list[Evidence]:
        out: list[Evidence] = []
        settled = [x for x in self.totals.exposures if x.settled]
        if settled:
            out.append(Evidence(metric="vertical_entry_offset_deg", value=round(statistics.median(x.ey for x in settled), 3),
                                unit="deg", samples=len(settled), method=METHOD_PLACEMENT))
            out.append(Evidence(metric="vertical_entry_abs_offset_deg",
                                value=round(statistics.median(abs(x.ey) for x in settled), 3), unit="deg",
                                samples=len(settled), method=METHOD_PLACEMENT + " Absolute value."))
            out.append(Evidence(metric="horizontal_entry_abs_offset_deg",
                                value=round(statistics.median(abs(x.ex) for x in settled), 3), unit="deg",
                                samples=len(settled), method=METHOD_HORIZONTAL))
        acq = list(self.totals.acquisitions)
        if acq:
            out.append(Evidence(metric="acquisition_time_ms", value=round(statistics.median(a[1] for a in acq), 1),
                                unit="ms", samples=len(acq), method=METHOD_ACQUISITION))
        fl = list(self.totals.flicks)
        if fl:
            out.append(Evidence(metric="overshoot_flicks", value=float(sum(1 for f in fl if f[1] == "overshoot")),
                                unit="flicks", samples=len(fl), method=METHOD_FLICK))
            out.append(Evidence(metric="undershoot_flicks", value=float(sum(1 for f in fl if f[1] == "undershoot")),
                                unit="flicks", samples=len(fl), method=METHOD_FLICK))
        shots = list(self.totals.shots)
        timed = [s for s in shots if s[1] is not None]
        if timed:
            out.append(Evidence(metric="unstable_shots", value=float(sum(1 for s in timed if s[1] > UNSTABLE_DPS)),
                                unit="shots", samples=len(timed), method=METHOD_SHOTS))
        moving = [s for s in shots if s[2] is not None]
        if moving:
            out.append(Evidence(metric="moving_shots", value=float(sum(1 for s in moving if s[2])), unit="shots",
                                samples=len(moving), method=METHOD_SHOTS))
        return out
