"""View-motion estimation by phase correlation between consecutive analyzed frames.

This measures *observable* cursor/view motion directly from pixels. It cannot
separate camera rotation from player translation (parallax), so results are
labelled "view motion", and low correlation response marks the sample as
unmeasurable instead of guessing. Screen-fixed overlays and detected moving
targets are masked (filled with the frame mean) so they cannot bias the
estimate.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from tari_schema import EgoMotion, Point2

from .frames import FrameView
from .geometry import Projection

MIN_RESPONSE = 0.35  # below this the correlation peak is unreliable (measured on real Lab recordings)
MAX_SHIFT_FRACTION = 0.35
MIN_TEXTURE = 1.5  # Laplacian std on the work image; below this, motion is unobservable

Zone = tuple[float, float, float, float]  # source px (x0, y0, x1, y1)


class EgoMotionEstimator:
    name = "ego_motion"

    def __init__(self, work_width: int = 256):
        self.work_width = work_width
        self._prev: np.ndarray | None = None  # unmasked work image of the previous frame
        self._prev_zones: list[Zone] = []
        self._prev_ts: float | None = None
        self._prev_key: tuple[int, int, int, int] | None = None
        self._window: np.ndarray | None = None

    def reset(self) -> None:
        self._prev = None
        self._prev_zones = []
        self._prev_ts = None
        self._prev_key = None

    def _masked(self, img: np.ndarray, zones: list[Zone], frame_w: int, frame_h: int) -> np.ndarray:
        out = img.copy()
        fill = float(img.mean())
        h, w = img.shape
        sx, sy = w / frame_w, h / frame_h
        for x0, y0, x1, y1 in zones:
            out[max(0, int(y0 * sy) - 1):max(0, int(np.ceil(y1 * sy)) + 1),
                max(0, int(x0 * sx) - 1):max(0, int(np.ceil(x1 * sx)) + 1)] = fill
        return out

    def estimate(self, frame: FrameView, projection: Projection, static_zones: list[Zone] | None = None) -> EgoMotion | None:
        """Estimate view motion. ``static_zones`` (HUD, crosshair) are masked so screen-fixed
        overlays cannot pull the estimate toward zero."""
        full = frame.full()
        work_h = max(16, int(round(self.work_width * full.height / full.width)))
        raw = cv2.resize(full.gray(), (self.work_width, work_h), interpolation=cv2.INTER_AREA).astype(np.float32)
        zones = list(static_zones or [])
        key = (frame.width, frame.height, self.work_width, work_h)
        ts = frame.ts_ms
        prev, prev_zones, prev_ts = self._prev, self._prev_zones, self._prev_ts
        same_geometry = self._prev_key == key
        self._prev, self._prev_zones, self._prev_ts, self._prev_key = raw, zones, ts, key
        if prev is None or prev_ts is None or not same_geometry or ts <= prev_ts:
            return None
        # Mask the union of both frames' zones in both images, so an object that appears,
        # disappears or changes color (e.g. a target's death flash) cannot bias the estimate.
        union = zones + prev_zones
        small = self._masked(raw, union, frame.width, frame.height)
        prev_m = self._masked(prev, union, frame.width, frame.height)
        texture = float(cv2.Laplacian(small, cv2.CV_32F).std())
        if self._window is None or self._window.shape != small.shape:
            self._window = cv2.createHanningWindow((self.work_width, work_h), cv2.CV_32F)
        (sx, sy), response = cv2.phaseCorrelate(prev_m, small, self._window)
        scale = frame.width / self.work_width
        dx, dy = float(sx) * scale, float(sy) * scale
        interval = ts - prev_ts
        measurable = (texture >= MIN_TEXTURE and response >= MIN_RESPONSE
                      and abs(sx) < MAX_SHIFT_FRACTION * self.work_width
                      and abs(sy) < MAX_SHIFT_FRACTION * work_h and math.isfinite(dx) and math.isfinite(dy))
        yaw, pitch = projection.shift_to_rotation(dx, dy)
        rate = 1000.0 / interval
        return EgoMotion(
            shift_px=Point2(x=round(dx, 3), y=round(dy, 3)),
            view_rate_dps=Point2(x=round(yaw * rate, 2), y=round(pitch * rate, 2)),
            interval_ms=round(interval, 3),
            response=round(float(response), 4),
            confidence=round(min(1.0, float(response) * 2.0), 3) if measurable else round(min(0.3, float(response)), 3),
            measurable=bool(measurable),
        )
