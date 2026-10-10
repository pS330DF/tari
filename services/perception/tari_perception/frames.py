"""Zero-copy numpy views over FramePacket regions with cached color conversions."""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from tari_schema import FramePacketHeader


@dataclass
class RegionView:
    name: str
    rgba: np.ndarray
    src_x: int
    src_y: int
    src_w: int
    src_h: int
    _cache: dict[str, np.ndarray] = field(default_factory=dict, repr=False)

    @property
    def width(self) -> int:
        return int(self.rgba.shape[1])

    @property
    def height(self) -> int:
        return int(self.rgba.shape[0])

    @property
    def scale_x(self) -> float:
        return self.src_w / self.width

    @property
    def scale_y(self) -> float:
        return self.src_h / self.height

    def to_source(self, u: float, v: float) -> tuple[float, float]:
        return self.src_x + u * self.scale_x, self.src_y + v * self.scale_y

    def from_source(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.src_x) / self.scale_x, (y - self.src_y) / self.scale_y

    def contains_source(self, x: float, y: float, margin: float = 0.0) -> bool:
        return (self.src_x + margin <= x <= self.src_x + self.src_w - margin
                and self.src_y + margin <= y <= self.src_y + self.src_h - margin)

    def rgb(self) -> np.ndarray:
        if "rgb" not in self._cache:
            self._cache["rgb"] = cv2.cvtColor(self.rgba, cv2.COLOR_RGBA2RGB)
        return self._cache["rgb"]

    def hsv(self) -> np.ndarray:
        if "hsv" not in self._cache:
            self._cache["hsv"] = cv2.cvtColor(self.rgb(), cv2.COLOR_RGB2HSV)
        return self._cache["hsv"]

    def gray(self) -> np.ndarray:
        if "gray" not in self._cache:
            self._cache["gray"] = cv2.cvtColor(self.rgba, cv2.COLOR_RGBA2GRAY)
        return self._cache["gray"]


@dataclass
class FrameView:
    header: FramePacketHeader
    regions: dict[str, RegionView]

    @property
    def width(self) -> int:
        return self.header.source_width

    @property
    def height(self) -> int:
        return self.header.source_height

    @property
    def ts_ms(self) -> float:
        return self.header.acquired_ts_ms

    def region(self, name: str) -> RegionView | None:
        return self.regions.get(name)

    def full(self) -> RegionView:
        region = self.regions.get("full")
        if region is None:
            raise KeyError("frame has no 'full' region")
        return region

    @classmethod
    def from_packet(cls, header: FramePacketHeader, payload: memoryview) -> "FrameView":
        regions: dict[str, RegionView] = {}
        for r in header.regions:
            arr = np.frombuffer(payload, dtype=np.uint8, count=r.byte_length, offset=r.byte_offset)
            arr = arr.reshape(r.height, r.width, 4)
            regions[r.name] = RegionView(r.name, arr, r.src_rect.x, r.src_rect.y, r.src_rect.w, r.src_rect.h)
        return cls(header, regions)
