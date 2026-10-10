"""Coaching orchestrator: routes events to coaches, filters, and emits outputs.

Only coaches with a working streaming implementation are registered. Domains
without one are reported as planned in the engine capabilities, never faked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tari_schema import (
    CoachingEvent, CoachingRecommendation, CoachingSettings, Evidence, GameState, OverlayInstruction, VoiceInstruction,
)
from tari_state import PolicyDecision

from .aim import AimCoach
from .filter import PriorityConfidenceFilter
from .overlay import OverlayBuilder
from .voice import VoiceBuilder

LIVE_DOMAINS = ["aim"]
PLANNED_DOMAINS = ["utility", "positioning", "tactical", "agent", "team", "communication"]


@dataclass
class CoachingOutput:
    recommendations: list[CoachingRecommendation] = field(default_factory=list)
    overlays: list[OverlayInstruction] = field(default_factory=list)
    voice: list[VoiceInstruction] = field(default_factory=list)


class CoachingOrchestrator:
    def __init__(self, session_id: str, settings: CoachingSettings, hfov_deg: float = 103.0):
        self.session_id = session_id
        self.hfov_deg = hfov_deg
        self.aim = AimCoach(session_id, settings)
        self.filter = PriorityConfidenceFilter(settings)
        self.voice = VoiceBuilder(session_id, settings)
        self.overlay = OverlayBuilder(self.aim.phraser)
        self.settings = settings
        self._last_mode: str | None = None
        self.active: list[CoachingRecommendation] = []

    def configure(self, settings: CoachingSettings, hfov_deg: float | None = None) -> None:
        self.settings = settings
        self.aim.configure(settings)
        self.filter.configure(settings)
        self.voice.configure(settings)
        self.overlay = OverlayBuilder(self.aim.phraser)
        if hfov_deg is not None:
            self.hfov_deg = hfov_deg

    def process(self, state: GameState, events: list[CoachingEvent], decision: PolicyDecision,
                source_size: tuple[int, int], trails: dict[int, list[tuple[float, float, float]]],
                now_ms: float) -> CoachingOutput:
        out = CoachingOutput()
        if decision.mode != self._last_mode:
            if decision.live_coaching_allowed:
                out.voice += self.voice.system(self.aim.phraser.system("lab_live"), "system.live", state.ts_ms, "P2")
            elif self._last_mode is not None:
                out.voice += self.voice.system(self.aim.phraser.system("paused"), "system.paused", state.ts_ms, "P0")
            self._last_mode = decision.mode
        if not decision.live_coaching_allowed:
            self.active = []
            return out

        candidates = self.aim.observe(events, state, state.ts_ms)
        accepted = self.filter.apply(candidates, state.ts_ms)
        types = {e.type for e in events}
        self.active = [r for r in self.active
                       if r.expiration.expires_ts_ms > state.ts_ms and r.expiration.until_event not in types]
        self.active.extend(accepted)
        out.recommendations = accepted
        out.voice += self.voice.from_recommendations(accepted)
        if decision.spatial_overlays_allowed:
            out.overlays.append(self.overlay.build(state, self.aim.flashes, self.settings.overlay_density,
                                                   self.hfov_deg, source_size, trails, now_ms))
        return out

    def summary(self) -> list[Evidence]:
        return self.aim.summary()
