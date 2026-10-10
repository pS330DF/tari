from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import TariModel, VersionedModel


class LatencyStats(TariModel):
    count: int
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None
    mean: float | None = None
    max: float | None = None


class PerformanceMetric(VersionedModel):
    name: str
    value: float | None
    unit: str
    ts_ms: float
    source: Literal["engine", "desktop"]
    available: bool = True
    note: str | None = None


class PerformanceSnapshot(VersionedModel):
    ts_ms: float
    window_s: float
    source: Literal["engine", "desktop"]
    latencies: dict[str, LatencyStats] = Field(default_factory=dict)
    rates: dict[str, float] = Field(default_factory=dict)
    counters: dict[str, int] = Field(default_factory=dict)
    gauges: dict[str, float | None] = Field(default_factory=dict)
    unavailable: dict[str, str] = Field(default_factory=dict, description="metric -> reason it cannot be measured")
