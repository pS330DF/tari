"""Rolling performance telemetry with p50/p95/p99 and resource sampling.

Metrics that cannot be measured on the current machine are reported in
``unavailable`` with a reason instead of being estimated.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

import numpy as np
import psutil

from tari_schema import LatencyStats, PerformanceSnapshot


def now_ms() -> float:
    return time.time() * 1000.0


def latency_stats(values: list[float] | np.ndarray) -> LatencyStats:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return LatencyStats(count=0)
    p50, p95, p99 = np.percentile(arr, [50, 95, 99])
    return LatencyStats(count=int(arr.size), p50=round(float(p50), 3), p95=round(float(p95), 3),
                        p99=round(float(p99), 3), mean=round(float(arr.mean()), 3), max=round(float(arr.max()), 3))


class GpuProbe:
    """GPU utilization via NVML when an NVIDIA GPU and pynvml are present."""

    def __init__(self) -> None:
        self.handle = None
        self.reason = "no supported GPU telemetry backend (NVML) on this system"
        try:
            import pynvml  # type: ignore[import-not-found]

            pynvml.nvmlInit()
            self._nvml = pynvml
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:  # noqa: BLE001 - absence of NVML is a normal condition
            self.handle = None

    def utilization(self) -> float | None:
        if self.handle is None:
            return None
        try:
            return float(self._nvml.nvmlDeviceGetUtilizationRates(self.handle).gpu)
        except Exception:  # noqa: BLE001
            return None


class ResourceSampler:
    def __init__(self) -> None:
        self.proc = psutil.Process(os.getpid())
        self.proc.cpu_percent(None)
        psutil.cpu_percent(None)
        self.gpu = GpuProbe()

    def sample(self) -> tuple[dict[str, float | None], dict[str, str]]:
        gauges: dict[str, float | None] = {
            "engine_cpu_percent": round(self.proc.cpu_percent(None), 1),
            "engine_rss_mb": round(self.proc.memory_info().rss / 1e6, 1),
            "system_cpu_percent": round(psutil.cpu_percent(None), 1),
            "system_memory_percent": round(psutil.virtual_memory().percent, 1),
        }
        unavailable: dict[str, str] = {}
        gpu = self.gpu.utilization()
        if gpu is None:
            unavailable["gpu_utilization_percent"] = self.gpu.reason
        else:
            gauges["gpu_utilization_percent"] = gpu
        return gauges, unavailable


class Telemetry:
    def __init__(self, window_s: float = 10.0, source: str = "engine", sampler: ResourceSampler | None = None):
        self.window_ms = window_s * 1000.0
        self.source = source
        self._lat: dict[str, deque[tuple[float, float]]] = defaultdict(deque)
        self._marks: dict[str, deque[float]] = defaultdict(deque)
        self.counters: dict[str, int] = defaultdict(int)
        self.gauges: dict[str, float | None] = {}
        self.sampler = sampler

    def record(self, name: str, value_ms: float, ts: float | None = None) -> None:
        self._lat[name].append((ts if ts is not None else now_ms(), value_ms))

    def mark(self, name: str, ts: float | None = None) -> None:
        self._marks[name].append(ts if ts is not None else now_ms())

    def count(self, name: str, n: int = 1) -> None:
        self.counters[name] += n

    def gauge(self, name: str, value: float | None) -> None:
        self.gauges[name] = value

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_ms
        for dq in self._lat.values():
            while dq and dq[0][0] < cutoff:
                dq.popleft()
        for mq in self._marks.values():
            while mq and mq[0] < cutoff:
                mq.popleft()

    def latencies(self, name: str) -> list[float]:
        return [v for _, v in self._lat.get(name, ())]

    def snapshot(self, now: float | None = None) -> PerformanceSnapshot:
        now = now if now is not None else now_ms()
        self._prune(now)
        gauges = dict(self.gauges)
        unavailable: dict[str, str] = {}
        if self.sampler is not None:
            g, u = self.sampler.sample()
            gauges.update(g)
            unavailable.update(u)
        rates = {}
        for name, mq in self._marks.items():
            if len(mq) >= 2:
                span = (mq[-1] - mq[0]) / 1000.0
                rates[name] = round((len(mq) - 1) / span, 2) if span > 0 else 0.0
            else:
                rates[name] = 0.0
        return PerformanceSnapshot(
            ts_ms=now, window_s=self.window_ms / 1000.0, source=self.source,  # type: ignore[arg-type]
            latencies={k: latency_stats([v for _, v in dq]) for k, dq in self._lat.items()},
            rates=rates, counters=dict(self.counters), gauges=gauges, unavailable=unavailable,
        )
