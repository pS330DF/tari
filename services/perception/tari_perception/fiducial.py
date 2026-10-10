"""Environment verification via the Training Lab's ArUco fiducial.

Live spatial coaching is only enabled when this marker is observed, which is
how TARI distinguishes its own controlled training environment from any other
captured window (including VALORANT, which stays gated behind authorization).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from tari_schema import EnvironmentObservation, Point2

from .frames import FrameView

FULL_SCAN_EVERY = 8


class FiducialDetector:
    name = "environment"

    def __init__(self, profile: dict[str, Any]):
        fid = profile["fiducial"]
        self.marker_id = int(fid["marker_id"])
        self.environment = str(fid["environment"])
        frame_box = profile["hud"]["fiducial_frame"]
        panel = profile["hud"]["panel"]
        # HUD cluster extent in marker units (x0, y0, x1, y1), used to mask screen-fixed pixels.
        self.hud_extent = (frame_box[0], frame_box[1], panel[0] + panel[2], frame_box[1] + frame_box[3])
        self.map_id = str(fid.get("map_id")) if fid.get("map_id") else None
        dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, fid["dictionary"]))
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self._detector = cv2.aruco.ArucoDetector(dictionary, params)
        self._last_roi: tuple[int, int, int, int] | None = None
        self._frames_since_full = FULL_SCAN_EVERY

    def reset(self) -> None:
        self._last_roi = None
        self._frames_since_full = FULL_SCAN_EVERY

    def detect(self, frame: FrameView) -> EnvironmentObservation:
        full = frame.full()
        gray = full.gray()
        corners = None
        if self._last_roi is not None:
            x0, y0, x1, y1 = self._last_roi
            corners = self._detect_in(gray[y0:y1, x0:x1], x0, y0)
        if corners is None:
            self._frames_since_full += 1
            if self._last_roi is not None or self._frames_since_full >= FULL_SCAN_EVERY:
                self._frames_since_full = 0
                corners = self._detect_in(gray, 0, 0)
        if corners is None:
            self._last_roi = None
            return EnvironmentObservation(kind="unknown", confidence=0.0)
        xs, ys = corners[:, 0], corners[:, 1]
        side = float(max(xs.max() - xs.min(), ys.max() - ys.min()))
        pad = int(side * 1.5) + 4
        self._last_roi = (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
                          min(full.width, int(xs.max()) + pad), min(full.height, int(ys.max()) + pad))
        sides = [float(np.linalg.norm(corners[i] - corners[(i + 1) % 4])) for i in range(4)]
        squareness = min(sides) / max(max(sides), 1e-6)
        conf = 0.95 if squareness > 0.8 else 0.6
        pts = []
        for cx, cy in corners:
            sx, sy = full.to_source(float(cx), float(cy))
            pts.append(Point2(x=sx / frame.width, y=sy / frame.height))
        return EnvironmentObservation(kind="training_lab", marker_id=self.marker_id, map_id=self.map_id,
                                      corners=pts, confidence=conf)

    def hud_zone(self, env: EnvironmentObservation, width: int, height: int) -> tuple[float, float, float, float] | None:
        """Source-pixel bounding box of the screen-fixed HUD cluster anchored to the marker."""
        if env.kind != "training_lab" or len(env.corners) != 4:
            return None
        c = np.array([[p.x * width, p.y * height] for p in env.corners])
        origin, ax, ay = c[0], c[1] - c[0], c[3] - c[0]
        u0, v0, u1, v1 = self.hud_extent
        pts = np.array([origin + u * ax + v * ay for u in (u0, u1) for v in (v0, v1)])
        return float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())

    def _detect_in(self, gray: np.ndarray, ox: int, oy: int) -> np.ndarray | None:
        if gray.size == 0:
            return None
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None:
            return None
        for c, i in zip(corners, ids.flatten()):
            if int(i) == self.marker_id:
                pts = c.reshape(4, 2).astype(np.float64)
                # OpenCV reports pixel-center coordinates; convert to edge convention.
                pts[:, 0] += ox + 0.5
                pts[:, 1] += oy + 0.5
                return pts
        return None
