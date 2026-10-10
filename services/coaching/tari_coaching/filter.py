"""Priority / confidence filter between the coaches and the player.

Rejects low-confidence recommendations, suppresses duplicates within a
cooldown, and rate-limits non-critical feedback according to the coaching
intensity setting. P0 (system/safety) always passes the rate limit, and lower
priority feedback never blocks higher priority feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tari_schema import PRIORITY_RANK, CoachingRecommendation, CoachingSettings

COOLDOWN_MS = {"low": 60_000.0, "balanced": 30_000.0, "high": 18_000.0}
MIN_GAP_MS = {"low": 12_000.0, "balanced": 6_000.0, "high": 3_000.0}


@dataclass
class FilterStats:
    accepted: int = 0
    low_confidence: int = 0
    duplicate: int = 0
    rate_limited: int = 0
    out_of_focus: int = 0
    reasons: list[tuple[str, str]] = field(default_factory=list)


class PriorityConfidenceFilter:
    def __init__(self, settings: CoachingSettings):
        self.stats = FilterStats()
        self._last_by_key: dict[str, float] = {}
        self._last_by_rank: dict[int, float] = {}
        self.configure(settings)

    def configure(self, settings: CoachingSettings) -> None:
        self.settings = settings
        self.cooldown_ms = COOLDOWN_MS[settings.intensity]
        self.min_gap_ms = MIN_GAP_MS[settings.intensity]

    def apply(self, recs: list[CoachingRecommendation], now_ms: float) -> list[CoachingRecommendation]:
        accepted: list[CoachingRecommendation] = []
        for rec in sorted(recs, key=lambda r: (PRIORITY_RANK[r.priority], -r.confidence)):
            reason = self._reject_reason(rec, now_ms)
            if reason:
                setattr(self.stats, reason, getattr(self.stats, reason) + 1)
                self.stats.reasons.append((rec.rule_id, reason))
                del self.stats.reasons[:-50]
                continue
            self._last_by_key[rec.dedupe_key] = now_ms
            self._last_by_rank[PRIORITY_RANK[rec.priority]] = now_ms
            self.stats.accepted += 1
            accepted.append(rec)
        return accepted

    def _reject_reason(self, rec: CoachingRecommendation, now_ms: float) -> str | None:
        if rec.priority != "P0" and rec.domain not in self.settings.focus and rec.domain != "system":
            return "out_of_focus"
        if rec.confidence < self.settings.min_confidence:
            return "low_confidence"
        last = self._last_by_key.get(rec.dedupe_key)
        if last is not None and now_ms - last < self.cooldown_ms:
            return "duplicate"
        if rec.priority != "P0":
            # Only feedback of equal or higher urgency counts against the gap, so a
            # P2 explanation can never hold back P1 training feedback.
            rank = PRIORITY_RANK[rec.priority]
            recent = [t for r, t in self._last_by_rank.items() if 0 < r <= rank]
            if recent and now_ms - max(recent) < self.min_gap_ms:
                return "rate_limited"
        return None
