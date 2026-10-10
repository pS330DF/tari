"""Shot detection from HUD ammo readings with one-frame confirmation.

A decrement is only reported once the next valid reading does not revert it,
so a single misread digit cannot create a phantom shot. Timing uses the frame
where the decrement first appeared (resolution = analyzed-frame interval).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ConfirmedShot:
    shots: int
    ts_ms: float
    frame_id: int
    snapshot: dict[str, Any]


@dataclass
class _Pending:
    value: int
    prev: int
    ts_ms: float
    frame_id: int
    snapshot: dict[str, Any]


class ShotDetector:
    def __init__(self, min_confidence: float = 0.6, max_step: int = 5):
        self.min_confidence = min_confidence
        self.max_step = max_step
        self.last: int | None = None
        self.pending: _Pending | None = None

    def reset(self) -> None:
        self.last = None
        self.pending = None

    def update(self, value: int | None, confidence: float, ts_ms: float, frame_id: int,
               snapshot: dict[str, Any]) -> list[ConfirmedShot]:
        if value is None or confidence < self.min_confidence:
            return []
        out: list[ConfirmedShot] = []
        if self.pending is not None:
            p, self.pending = self.pending, None
            if value <= p.value:
                out.append(ConfirmedShot(p.prev - p.value, p.ts_ms, p.frame_id, p.snapshot))
                self.last = p.value
        if self.last is None:
            self.last = value
        elif value < self.last:
            if self.last - value <= self.max_step:
                self.pending = _Pending(value, self.last, ts_ms, frame_id, snapshot)
            else:
                self.last = value  # implausible jump: resynchronize without inventing shots
        elif value > self.last:
            self.last = value  # reload
        return out
