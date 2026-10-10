"""Color helpers: HSV masks for crosshair colors and target highlight presets."""

from __future__ import annotations

import cv2
import numpy as np


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hsv_cv(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    px = np.uint8([[list(rgb)]])
    h, s, v = cv2.cvtColor(px, cv2.COLOR_RGB2HSV)[0, 0]
    return int(h), int(s), int(v)


HsvRange = tuple[int, int, int, int, int, int]


def crosshair_ranges(hex_color: str, hue_band: int = 7) -> list[HsvRange]:
    """HSV ranges matching a crosshair color, handling white and hue wrap-around."""
    h, s, v = rgb_to_hsv_cv(hex_to_rgb(hex_color))
    if s < 40:  # white / light gray crosshair: match bright, unsaturated pixels
        return [(0, 0, max(185, v - 45), 180, 60, 255)]
    s_min = max(80, int(s * 0.55))
    v_min = max(90, int(v * 0.5))
    lo, hi = h - hue_band, h + hue_band
    if lo < 0:
        return [(0, s_min, v_min, hi, 255, 255), (180 + lo, s_min, v_min, 180, 255, 255)]
    if hi > 180:
        return [(lo, s_min, v_min, 180, 255, 255), (0, s_min, v_min, hi - 180, 255, 255)]
    return [(lo, s_min, v_min, hi, 255, 255)]


def mask_from_ranges(hsv: np.ndarray, ranges: list[HsvRange]) -> np.ndarray:
    mask: np.ndarray | None = None
    for r in ranges:
        m = cv2.inRange(hsv, np.array(r[:3], dtype=np.uint8), np.array(r[3:], dtype=np.uint8))
        mask = m if mask is None else cv2.bitwise_or(mask, m)
    assert mask is not None
    return mask
