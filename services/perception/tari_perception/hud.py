"""HUD interpretation for the Training Lab profile (seven-segment readouts).

The HUD layout is anchored to the fiducial marker, so readout positions are
resolution independent. Each digit is decoded by sampling segment centerlines
(at three offsets across the segment, keeping the brightest) and thresholding
between the brightest and darkest segment of the readout. A small grid of
sub-cell offsets is evaluated in one vectorized pass to absorb marker
registration error; the offset with the largest decode margin wins.

An unreadable digit invalidates the readout (value=None); it is never guessed.
Other HUD profiles (e.g. a real game HUD) would plug an OCR backend in behind
the same ``parse`` interface; none is bundled yet.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from tari_schema import EnvironmentObservation, HudReading, HudReadout

from .frames import FrameView

MIN_CONTRAST = 50.0
ALIGN_OFFSETS = np.array([-0.06, -0.03, 0.0, 0.03, 0.06])  # marker units
SEG_ORDER = "abcdefg"
LENGTH_T = np.array([0.3, 0.4, 0.5, 0.6, 0.7])
THICK_T = np.array([-0.35, 0.0, 0.35])


class SevenSegmentHudParser:
    name = "hud"

    def __init__(self, profile: dict[str, Any]):
        hud = profile["hud"]
        self.profile_id = str(profile["id"])
        self.readouts: dict[str, dict[str, Any]] = hud["readouts"]
        # Lookup: 7-bit lit-segment code -> digit (or -1).
        self.lut = np.full(128, -1, dtype=np.int16)
        for digit, segs in hud["digit_patterns"].items():
            code = sum(1 << SEG_ORDER.index(c) for c in segs)
            self.lut[code] = int(digit)
        # Sample points per segment in digit-cell coordinates: shape (7, thick, length, 2).
        pts = np.zeros((7, len(THICK_T), len(LENGTH_T), 2))
        for i, seg in enumerate(SEG_ORDER):
            x0, y0, x1, y1 = hud["segments"][seg]
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            horizontal = (x1 - x0) >= (y1 - y0) * 0.76 / 0.44
            for a, off in enumerate(THICK_T):
                for b, t in enumerate(LENGTH_T):
                    if horizontal:
                        pts[i, a, b] = (x0 + t * (x1 - x0), my + off * (y1 - y0))
                    else:
                        pts[i, a, b] = (mx + off * (x1 - x0), y0 + t * (y1 - y0))
        self.cell_pts = pts

    def parse(self, frame: FrameView, env: EnvironmentObservation | None) -> HudReading | None:
        if env is None or env.kind != "training_lab" or len(env.corners) != 4:
            return None
        full = frame.full()
        gray = full.gray()
        c = [full.from_source(p.x * frame.width, p.y * frame.height) for p in env.corners]
        origin = np.array(c[0])
        ax = np.array(c[1]) - origin
        ay = np.array(c[3]) - origin
        out = [self._read(gray, name, spec, origin, ax, ay) for name, spec in self.readouts.items()]
        return HudReading(profile=self.profile_id, readouts=out)

    def _read(self, gray: np.ndarray, name: str, spec: dict[str, Any], origin: np.ndarray, ax: np.ndarray,
              ay: np.ndarray) -> HudReadout:
        n = int(spec["digits"])
        dw, dh, pitch = float(spec["digit_w"]), float(spec["digit_h"]), float(spec["pitch"])
        # Marker-unit coordinates for every (du, dv, digit, segment, thick, length) sample.
        k = np.arange(n)
        u = (float(spec["x"]) + ALIGN_OFFSETS[:, None, None, None, None, None]
             + (k * pitch)[None, None, :, None, None, None]
             + self.cell_pts[None, None, None, :, :, :, 0] * dw)
        v = (float(spec["y"]) + ALIGN_OFFSETS[None, :, None, None, None, None]
             + self.cell_pts[None, None, None, :, :, :, 1] * dh)
        u, v = np.broadcast_arrays(u, v)
        px = origin[0] + u * ax[0] + v * ay[0]
        py = origin[1] + u * ax[1] + v * ay[1]
        samples = _bilinear(gray, px, py)  # (5, 5, n, 7, 3, 5)
        seg = samples.mean(axis=-1).max(axis=-1)  # (5, 5, n, 7)
        # Dark reference: panel background inside each digit's two enclosed holes, so a
        # readout with every segment lit (e.g. "88") still has something to threshold against.
        hu = (float(spec["x"]) + ALIGN_OFFSETS[:, None, None, None] + (k * pitch)[None, None, :, None]
              + 0.5 * dw + 0.0 * ALIGN_OFFSETS[None, :, None, None])
        hv = float(spec["y"]) + ALIGN_OFFSETS[None, :, None, None] + np.array([0.27, 0.73])[None, None, None, :] * dh
        hu, hv = np.broadcast_arrays(hu, hv)
        holes = _bilinear(gray, origin[0] + hu * ax[0] + hv * ay[0], origin[1] + hu * ax[1] + hv * ay[1])
        flat = seg.reshape(seg.shape[0], seg.shape[1], -1)
        lo = np.minimum(flat.min(axis=-1), holes.reshape(holes.shape[0], holes.shape[1], -1).min(axis=-1))
        hi = flat.max(axis=-1)  # (5, 5)
        contrast = hi - lo
        thr = ((lo + hi) / 2.0)[:, :, None, None]
        half = np.maximum(contrast / 2.0, 1e-6)[:, :, None, None]
        lit = seg > thr
        codes = (lit * (1 << np.arange(7))).sum(axis=-1)  # (5, 5, n)
        digits = self.lut[codes]
        margins = np.abs(seg - thr) / half  # (5, 5, n, 7)
        valid = (digits >= 0).all(axis=-1) & (contrast >= MIN_CONTRAST)
        if not valid.any():
            center = len(ALIGN_OFFSETS) // 2
            raw = "".join(str(d) if d >= 0 else "?" for d in digits[center, center])
            return HudReadout(name=name, value=None, raw=raw if contrast[center, center] >= MIN_CONTRAST else None,
                              confidence=0.0)
        min_margin = margins.min(axis=(-1, -2))
        score = np.where(valid, min_margin + 0.01 * margins.sum(axis=(-1, -2)), -1.0)
        i, j = np.unravel_index(int(np.argmax(score)), score.shape)
        raw = "".join(str(int(d)) for d in digits[i, j])
        conf = round(0.5 + 0.5 * min(1.0, float(min_margin[i, j])), 3)
        return HudReadout(name=name, value=int(raw), raw=raw, confidence=conf)


def _bilinear(gray: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Bilinear samples at edge-convention points (pixel i spans [i, i+1))."""
    h, w = gray.shape
    x = np.clip(xs - 0.5, 0, w - 1.001)
    y = np.clip(ys - 0.5, 0, h - 1.001)
    x0 = x.astype(np.int32)
    y0 = y.astype(np.int32)
    fx, fy = x - x0, y - y0
    g00 = gray[y0, x0].astype(np.float32)
    g01 = gray[y0, x0 + 1].astype(np.float32)
    g10 = gray[y0 + 1, x0].astype(np.float32)
    g11 = gray[y0 + 1, x0 + 1].astype(np.float32)
    return g00 * (1 - fx) * (1 - fy) + g01 * fx * (1 - fy) + g10 * (1 - fx) * fy + g11 * fx * fy
