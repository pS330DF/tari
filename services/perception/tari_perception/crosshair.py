"""Crosshair detection on the unscaled center crop.

The crosshair is located as a symmetric set of thin arms in the configured
color. When no crosshair is found the analyzer returns the frame center as an
*estimate* (method ``assumed_center``) with low confidence; downstream rules
treat that as insufficient for placement measurements.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2

from tari_schema import CrosshairObservation, Point2

from .color import crosshair_ranges, mask_from_ranges
from .frames import FrameView, RegionView

ASSUMED_CENTER_CONFIDENCE = 0.3


@dataclass
class _Arm:
    left: float
    top: float
    w: float
    h: float
    area: int

    @property
    def right(self) -> float:
        return self.left + self.w

    @property
    def bottom(self) -> float:
        return self.top + self.h

    @property
    def cx(self) -> float:
        return self.left + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.top + self.h / 2.0


@dataclass
class _Candidate:
    x: float
    y: float
    gap: float
    arms: int
    confidence: float
    extent: float = 0.0  # center to outer arm end, region px


class CrosshairAnalyzer:
    name = "crosshair"

    def __init__(self, color_hex: str = "#00f0ff", max_thickness_px: int = 8, max_arm_px: int = 60):
        self.max_thickness_px = max_thickness_px
        self.max_arm_px = max_arm_px
        self.configure(color_hex)

    def configure(self, color_hex: str) -> None:
        self.color_hex = color_hex
        self.ranges = crosshair_ranges(color_hex)
        self.last_zone: tuple[float, float, float, float] | None = None
        self.last_geometry: tuple[float, float, float, float] | None = None  # cx, cy, extent, half_thickness (src px)

    def occluder_zone(self) -> tuple[float, float, float, float] | None:
        """Source-pixel box (x0, y0, x1, y1) covered by the last detected crosshair incl. outline."""
        return self.last_zone

    def overlaps(self, x: float, y: float, r: float) -> bool:
        """True if a circle (source px) touches the last detected crosshair arms or outline."""
        if self.last_geometry is None:
            return False
        cx, cy, ext, ht = self.last_geometry
        dx, dy = abs(x - cx), abs(y - cy)
        return (dx <= ext + r and dy <= ht + r) or (dy <= ext + r and dx <= ht + r)

    def analyze(self, frame: FrameView) -> CrosshairObservation:
        region = frame.region("center") or frame.full()
        candidate = self._detect(region)
        self.last_zone = None
        self.last_geometry = None
        if candidate is not None:
            cx_s, cy_s = region.to_source(candidate.x, candidate.y)
            half = (max(candidate.extent, candidate.gap) + self.max_thickness_px / 2 + 2) * region.scale_x
            self.last_zone = (cx_s - half, cy_s - half, cx_s + half, cy_s + half)
            self.last_geometry = (cx_s, cy_s, (max(candidate.extent, candidate.gap) + 1) * region.scale_x,
                                  (self.max_thickness_px / 2) * region.scale_x)
        if candidate is None:
            return CrosshairObservation(
                position=Point2(x=0.5, y=0.5), method="assumed_center",
                confidence=ASSUMED_CENTER_CONFIDENCE, arm_gap_px=None, arms_found=0,
            )
        sx, sy = region.to_source(candidate.x, candidate.y)
        return CrosshairObservation(
            position=Point2(x=sx / frame.width, y=sy / frame.height),
            method="detected",
            confidence=round(candidate.confidence, 3),
            arm_gap_px=round(candidate.gap * region.scale_x, 2),
            arms_found=candidate.arms,
        )

    # -- internals ---------------------------------------------------------

    def _detect(self, region: RegionView) -> _Candidate | None:
        mask = mask_from_ranges(region.hsv(), self.ranges)
        n, _labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        horizontals: list[_Arm] = []
        verticals: list[_Arm] = []
        crosses: list[_Arm] = []
        t = self.max_thickness_px
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < 2 or max(w, h) > self.max_arm_px * 2:
                continue
            arm = _Arm(float(x), float(y), float(w), float(h), area)
            if w >= 2 * h and h <= t:
                horizontals.append(arm)
            elif h >= 2 * w and w <= t:
                verticals.append(arm)
            elif w >= 5 and h >= 5 and area / float(w * h) < 0.55:
                crosses.append(arm)  # connected "+" shape without a gap

        cands: list[_Candidate] = []
        hpairs = self._pairs(horizontals, axis="h")
        vpairs = self._pairs(verticals, axis="v")
        for hp in hpairs:
            for vp in vpairs:
                if abs(hp.x - vp.x) <= 3.0 and abs(hp.y - vp.y) <= 3.0:
                    asym = abs(hp.gap - vp.gap) + abs(hp.x - vp.x) + abs(hp.y - vp.y)
                    cands.append(_Candidate(
                        x=hp.x, y=vp.y, gap=(hp.gap + vp.gap) / 2.0, arms=4,
                        confidence=max(0.6, 0.97 - 0.05 * asym), extent=max(hp.extent, vp.extent),
                    ))
        if not cands:
            cands.extend(_Candidate(p.x, p.y, p.gap, 2, 0.7) for p in hpairs + vpairs)
        for c in crosses:
            cands.append(_Candidate(c.cx, c.cy, 0.0, 4, 0.85, extent=max(c.w, c.h) / 2.0))
        if not cands:
            return None
        cx, cy = region.width / 2.0, region.height / 2.0
        # Prefer high-confidence candidates close to the region center.
        return max(cands, key=lambda c: c.confidence - 0.004 * ((c.x - cx) ** 2 + (c.y - cy) ** 2) ** 0.5)

    @staticmethod
    def _pairs(arms: list[_Arm], axis: str) -> list[_Candidate]:
        out: list[_Candidate] = []
        for i, a in enumerate(arms):
            for b in arms[i + 1:]:
                if axis == "h":
                    first, second = (a, b) if a.left < b.left else (b, a)
                    if abs(first.cy - second.cy) > 2.0 or first.right > second.left:
                        continue
                    if abs(first.w - second.w) > max(2.0, 0.35 * max(first.w, second.w)):
                        continue
                    gap = (second.left - first.right) / 2.0
                    out.append(_Candidate((first.right + second.left) / 2.0, (first.cy + second.cy) / 2.0, gap, 2, 0.7,
                                          extent=gap + max(first.w, second.w)))
                else:
                    first, second = (a, b) if a.top < b.top else (b, a)
                    if abs(first.cx - second.cx) > 2.0 or first.bottom > second.top:
                        continue
                    if abs(first.h - second.h) > max(2.0, 0.35 * max(first.h, second.h)):
                        continue
                    gap = (second.top - first.bottom) / 2.0
                    out.append(_Candidate((first.cx + second.cx) / 2.0, (first.bottom + second.top) / 2.0, gap, 2, 0.7,
                                          extent=gap + max(first.h, second.h)))
        return out

