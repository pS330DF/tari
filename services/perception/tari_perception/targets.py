"""Target detection by highlight-color segmentation plus head localization.

Head localization uses the silhouette's row-width profile: the head is the
narrow top section above the jump to shoulder width. If no such jump is
visible (e.g. a sliver of a body emerging from cover) the estimate falls back
to fixed body ratios and the detection's confidence is reduced accordingly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from tari_schema import Point2, Rect, TargetDetection

from .color import HsvRange, mask_from_ranges
from .frames import FrameView, RegionView

Zone = tuple[float, float, float, float]  # source px (x0, y0, x1, y1)
OverlapFn = Callable[[float, float, float], bool]

METHOD_FACTOR = {"head_profile": 1.0, "refined_crop": 1.0, "top_ratio": 0.82, "blob_top": 0.68}


@dataclass
class HeadEstimate:
    x: float  # relative to the component bbox origin, region px
    y: float
    radius: float
    method: str


def estimate_head(comp: np.ndarray) -> HeadEstimate:
    """Locate the head inside a boolean component mask (rows x cols).

    Primary method ("head_profile"): the shoulder line is the first row whose
    width reaches 75% of the silhouette's maximum width. A head is present when
    the rows above it are clearly narrower (<= 70% of the max) and a body
    continues below. The head diameter is the widest row above the shoulders and
    the head center sits one radius below the silhouette top. This is robust to
    thin anti-aliased top rows and works for heads only a few pixels across.
    """
    h, w = comp.shape
    widths = comp.sum(axis=1).astype(np.float32)
    max_w = float(widths.max()) if h else 0.0

    if h >= 4 and max_w >= 3:
        wide = np.nonzero(widths >= 0.75 * max_w)[0]
        shoulder = int(wide[0]) if wide.size else h
        if 2 <= shoulder < h - 1:
            head_w = float(widths[:shoulder].max())
            below = widths[shoulder:]
            body = int((below >= 0.6 * max_w).sum()) >= max(2, int(0.3 * below.size))
            if head_w <= 0.7 * max_w and body and head_w >= 1.0:
                r = head_w / 2.0
                rows = min(shoulder, max(1, int(np.ceil(2 * r))))
                ys, xs = np.nonzero(comp[:rows])
                cx = float(xs.mean()) + 0.5 if xs.size else w / 2.0
                return HeadEstimate(cx, r, max(0.5, r), "head_profile")

    if h >= 1.8 * max(max_w, 1.0):
        top = max(1, int(0.15 * h))
        ys, xs = np.nonzero(comp[:top])
        cx = float(xs.mean()) + 0.5 if xs.size else w / 2.0
        return HeadEstimate(cx, 0.085 * h, max(1.0, 0.075 * h), "top_ratio")

    rows = max(1, min(h, int(max_w)))
    ys, xs = np.nonzero(comp[:rows])
    cx = float(xs.mean()) + 0.5 if xs.size else w / 2.0
    cy = float(ys.mean()) + 0.5 if ys.size else h / 2.0
    return HeadEstimate(cx, cy, max(1.0, max_w / 2.0), "blob_top")


def close_occluders(mask: np.ndarray, region: RegionView, occluders: list[Zone] | None) -> np.ndarray:
    """Fill thin cuts that an overlay (the crosshair and its outline) makes in target silhouettes.

    Closing is applied only inside the occluder zones, so silhouettes elsewhere
    are untouched.
    """
    if not occluders:
        return mask
    k = max(3, int(np.ceil(5 / region.scale_x)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    out = mask
    for x0, y0, x1, y1 in occluders:
        u0, v0 = region.from_source(x0, y0)
        u1, v1 = region.from_source(x1, y1)
        iu0, iv0 = max(0, int(u0) - k), max(0, int(v0) - k)
        iu1, iv1 = min(region.width, int(np.ceil(u1)) + k), min(region.height, int(np.ceil(v1)) + k)
        if iu1 - iu0 < k or iv1 - iv0 < k:
            continue
        if out is mask:
            out = mask.copy()
        out[iv0:iv1, iu0:iu1] = cv2.morphologyEx(mask[iv0:iv1, iu0:iu1], cv2.MORPH_CLOSE, kernel)
    return out


class ColorTargetDetector:
    name = "targets"
    backend = "color_hsv"

    def __init__(self, ranges: list[HsvRange], min_area_px: int = 30, max_targets: int = 12):
        self.ranges = ranges
        self.min_area_px = min_area_px
        self.max_targets = max_targets
        self._open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def configure(self, ranges: list[HsvRange]) -> None:
        self.ranges = ranges

    def segment(self, region: RegionView, occluders: list[Zone] | None = None) -> np.ndarray:
        mask = mask_from_ranges(region.hsv(), self.ranges)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._open)
        return close_occluders(mask, region, occluders)

    def detect(self, frame: FrameView, occluders: list[Zone] | None = None,
               overlaps: OverlapFn | None = None) -> list[TargetDetection]:
        """Detect targets. ``occluders`` are boxes where thin overlay cuts are closed;
        ``overlaps(x, y, r)`` reports whether a head circle touches the crosshair."""
        full = frame.full()
        mask = self.segment(full, occluders)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        dets: list[TargetDetection] = []
        order = sorted(range(1, n), key=lambda i: -int(stats[i][4]))[: self.max_targets]
        for i in order:
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < self.min_area_px:
                continue
            comp = labels[y:y + h, x:x + w] == i
            head = estimate_head(comp)
            hx, hy = full.to_source(x + head.x, y + head.y)
            radius_src = head.radius * full.scale_x
            method = head.method
            center = frame.region("center")
            if center is not None and center.contains_source(hx, hy, margin=radius_src * 3):
                refined = self._refine_in_crop(center, hx, hy, radius_src, occluders)
                if refined is not None:
                    hx, hy, radius_src = refined
                    method = "refined_crop"
            bx, by = full.to_source(x, y)
            area_src = int(area * full.scale_x * full.scale_y)
            size_factor = min(1.0, area / 150.0)
            sliver = w < 0.25 * h and method in ("top_ratio", "blob_top")
            conf = (0.75 + 0.2 * size_factor) * METHOD_FACTOR[method] * (0.7 if sliver else 1.0)
            overlap = bool(overlaps is not None and overlaps(hx, hy, radius_src))
            if overlap:
                conf *= 0.85  # head partly hidden behind the crosshair: localization is less certain
            dets.append(TargetDetection(
                bbox=Rect(x=bx / frame.width, y=by / frame.height,
                          w=w * full.scale_x / frame.width, h=h * full.scale_y / frame.height),
                head=Point2(x=hx / frame.width, y=hy / frame.height),
                head_radius=radius_src / frame.width,
                head_method=method,  # type: ignore[arg-type]
                confidence=round(min(conf, 0.97), 3),
                area_px=area_src,
                backend=self.backend,
                crosshair_overlap=overlap,
            ))
        return dets

    def _refine_in_crop(self, center: RegionView, hx: float, hy: float, r: float,
                        occluders: list[Zone] | None = None) -> tuple[float, float, float] | None:
        """Re-estimate the head on the unscaled crop for sub-pixel precision near the crosshair."""
        u, v = center.from_source(hx, hy)
        half_w = max(8, int(r * 4))
        x0, x1 = max(0, int(u - half_w)), min(center.width, int(u + half_w))
        y0, y1 = max(0, int(v - r * 3)), min(center.height, int(v + r * 8))
        if x1 - x0 < 4 or y1 - y0 < 6:
            return None
        full_mask = close_occluders(mask_from_ranges(center.hsv(), self.ranges), center, occluders)
        mask = full_mask[y0:y1, x0:x1]
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if n <= 1:
            return None
        lu, lv = int(u) - x0, int(v) - y0
        best = None
        best_d = 1e9
        for i in range(1, n):
            x, y, w, h, area = (int(s) for s in stats[i])
            if area < 6:
                continue
            dx = max(x - lu, 0, lu - (x + w))
            dy = max(y - lv, 0, lv - (y + h))
            d = dx * dx + dy * dy
            if d < best_d:
                best, best_d = i, d
        if best is None or best_d > (r * 2) ** 2:
            return None
        x, y, w, h, _ = (int(s) for s in stats[best])
        if y == 0:  # silhouette top is clipped by the window; cannot see the head top
            return None
        head = estimate_head(labels[y:y + h, x:x + w] == best)
        if head.method != "head_profile":
            return None
        sx, sy = center.to_source(x0 + x + head.x, y0 + y + head.y)
        return sx, sy, head.radius * center.scale_x
