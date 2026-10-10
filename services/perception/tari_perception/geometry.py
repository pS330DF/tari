"""Pinhole-projection helpers converting screen offsets to view angles.

Assumption (documented in docs/metrics.md): the analyzed frame equals the game
viewport and the horizontal FOV is known (VALORANT and the Training Lab both
use 103 degrees at 16:9). Pixels are square, so one focal length serves both axes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Projection:
    width: int
    height: int
    hfov_deg: float = 103.0

    @property
    def focal_px(self) -> float:
        return (self.width / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)

    def yaw_of(self, x_px: float) -> float:
        """View yaw (deg) of a screen column; positive to the right of center."""
        return math.degrees(math.atan((x_px - self.width / 2.0) / self.focal_px))

    def pitch_of(self, y_px: float) -> float:
        """View pitch (deg) of a screen row; positive above center."""
        return math.degrees(math.atan((self.height / 2.0 - y_px) / self.focal_px))

    def angular_offset(self, frm: tuple[float, float], to: tuple[float, float]) -> tuple[float, float]:
        """Angle from point ``frm`` to point ``to`` (deg): x>0 to the right, y>0 upward."""
        return (self.yaw_of(to[0]) - self.yaw_of(frm[0]), self.pitch_of(to[1]) - self.pitch_of(frm[1]))

    def length_deg(self, length_px: float) -> float:
        """Angular size of a length measured at the screen center."""
        return math.degrees(math.atan(abs(length_px) / self.focal_px))

    def shift_to_rotation(self, dx_px: float, dy_px: float) -> tuple[float, float]:
        """Convert a global content shift (prev->cur) to the view rotation that caused it.

        Content moving left means the view turned right; content moving down means
        the view pitched up.
        """
        yaw = -math.degrees(math.atan(dx_px / self.focal_px))
        pitch = math.degrees(math.atan(dy_px / self.focal_px))
        return yaw, pitch


def clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v
