"""Bounded frame scheduling: latest-frame-wins slot plus staleness policy.

Frames are never queued indefinitely. When the processor is busy, a newer
frame replaces the waiting one (the replaced frame is reported as
"superseded"); frames whose age exceeds ``max_age_ms`` when they reach the
processor are dropped as "stale".
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

from tari_schema import FramePacketHeader


@dataclass
class FrameItem:
    header: FramePacketHeader
    payload: memoryview
    received_ts_ms: float
    size_bytes: int


class LatestFrameSlot:
    def __init__(self, capacity: int = 1):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._items: deque[FrameItem] = deque()
        self._event = asyncio.Event()

    def put(self, item: FrameItem) -> FrameItem | None:
        """Insert a frame; returns the frame it displaced, if any."""
        dropped = None
        if len(self._items) >= self.capacity:
            dropped = self._items.popleft()
        self._items.append(item)
        self._event.set()
        return dropped

    async def get(self) -> FrameItem:
        while not self._items:
            self._event.clear()
            await self._event.wait()
        return self._items.popleft()

    def clear(self) -> list[FrameItem]:
        items = list(self._items)
        self._items.clear()
        return items

    @property
    def depth(self) -> int:
        return len(self._items)


def frame_age_ms(item: FrameItem, now_ms: float) -> float:
    return now_ms - item.header.acquired_ts_ms


def drop_reason(item: FrameItem, now_ms: float, max_age_ms: float, last_processed_ts: float | None) -> str | None:
    if last_processed_ts is not None and item.header.acquired_ts_ms <= last_processed_ts:
        return "out_of_order"
    if frame_age_ms(item, now_ms) > max_age_ms:
        return "stale"
    return None
