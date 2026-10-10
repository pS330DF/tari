"""State-field helpers: staleness, categorical hysteresis, observation provenance."""

from __future__ import annotations

from dataclasses import dataclass

from tari_schema import TextField


@dataclass
class CategoricalTracker:
    """Hysteresis for categorical labels (environment, map, agent).

    A new label replaces the current one only after ``confirm_n`` consecutive
    confident observations, so a single misidentification cannot flip state.
    The current label becomes ``stale`` once unconfirmed for ``ttl_ms``.
    """

    name: str
    source: str
    confirm_n: int = 3
    min_confidence: float = 0.6
    ttl_ms: float = 2000.0
    value: str | None = None
    confidence: float = 0.0
    last_confirmed_ts: float | None = None
    _candidate: str | None = None
    _candidate_count: int = 0

    def reset(self) -> None:
        self.value = None
        self.confidence = 0.0
        self.last_confirmed_ts = None
        self._candidate = None
        self._candidate_count = 0

    def update(self, label: str | None, confidence: float, ts_ms: float) -> bool:
        """Feed one observation. Returns True when the confirmed label changed."""
        if label is None or confidence < self.min_confidence:
            self._candidate, self._candidate_count = None, 0
            return False
        if label == self.value:
            self.last_confirmed_ts = ts_ms
            self.confidence = 0.7 * self.confidence + 0.3 * confidence
            self._candidate, self._candidate_count = None, 0
            return False
        if label == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate, self._candidate_count = label, 1
        if self._candidate_count >= self.confirm_n:
            self.value = label
            self.confidence = confidence
            self.last_confirmed_ts = ts_ms
            self._candidate, self._candidate_count = None, 0
            return True
        return False

    def field(self, now_ms: float, method: str) -> TextField:
        if self.value is None or self.last_confirmed_ts is None:
            return TextField(status="unknown", source=self.source, method=method,
                             reason="not yet identified" if self.value is None else None)
        age = now_ms - self.last_confirmed_ts
        if age > self.ttl_ms:
            return TextField(status="stale", value=self.value, confidence=round(self.confidence * 0.5, 3),
                             updated_ts_ms=self.last_confirmed_ts, source=self.source, method=method,
                             reason=f"not re-observed for {age:.0f} ms")
        return TextField(status="observed", value=self.value, confidence=round(self.confidence, 3),
                         updated_ts_ms=self.last_confirmed_ts, source=self.source, method=method)
