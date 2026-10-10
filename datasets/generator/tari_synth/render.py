"""Deterministic synthetic renderer for Training-Lab-style frames with ground truth.

This is a *simulated* video source for automated tests and evaluation only.
Frames it produces are tagged ``simulated=True`` in their FramePackets.

World model: positions are view angles (deg). The background is a textured
panorama translated by the view rotation; targets are projected with the same
pinhole model the engine uses, so ground-truth angles are exact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from tari_perception.kb import load_environment_profile
from tari_schema import FramePacketHeader, FrameRegion, PixelRect, encode_frame_packet


@dataclass
class SynthTarget:
    tid: int
    yaw: float
    pitch: float
    dist_m: float = 15.0
    visible: bool = True


@dataclass
class Cover:
    yaw0: float
    pitch0: float
    yaw1: float
    pitch1: float
    shade: int = 92


@dataclass
class FrameSpec:
    t_ms: float
    view_yaw: float = 0.0
    view_pitch: float = 0.0
    targets: list[SynthTarget] = field(default_factory=list)
    covers: list[Cover] = field(default_factory=list)
    crosshair_gap: float = 4.0
    crosshair_offset: tuple[int, int] = (0, 0)
    crosshair_color: tuple[int, int, int] = (0, 240, 255)
    draw_crosshair: bool = True
    ammo: int | None = 25
    timer: int | None = 60
    drill: int | None = 1
    draw_hud: bool = True
    draw_fiducial: bool = True
    target_color: str = "red"
    moving: bool = False
    shots: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetTruth:
    tid: int
    head_px: tuple[float, float]
    head_r_px: float
    head_visible: bool
    bbox_px: tuple[float, float, float, float]


@dataclass
class GroundTruth:
    t_ms: float
    width: int
    height: int
    crosshair_px: tuple[float, float]
    targets: list[TargetTruth]
    view: tuple[float, float]
    moving: bool
    ammo: int | None
    timer: int | None
    shots: int
    drill: int | None
    meta: dict[str, Any]


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class SyntheticRenderer:
    def __init__(self, width: int = 1920, height: int = 1080, hfov_deg: float = 103.0, seed: int = 7,
                 profile: dict[str, Any] | None = None, pan_margin_deg: float = 45.0):
        self.width, self.height, self.hfov = width, height, hfov_deg
        self.profile = profile or load_environment_profile()
        self.focal = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        self.deg_px = self.focal * math.pi / 180.0
        self.margin_x = int(pan_margin_deg * self.deg_px)
        self.margin_y = int(pan_margin_deg * 0.6 * self.deg_px)
        self.pano = self._make_panorama(seed)

    # -- background ------------------------------------------------------
    def _make_panorama(self, seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        h = self.height + 2 * self.margin_y
        w = self.width + 2 * self.margin_x
        base = np.linspace(48, 84, h, dtype=np.float32)[:, None].repeat(w, axis=1)
        img = np.stack([base + 6, base + 2, base - 4], axis=-1)  # slight cool tint (BGR)
        for _ in range(int(w * h / 9000)):
            x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
            rw, rh = int(rng.integers(20, 220)), int(rng.integers(20, 160))
            g = float(rng.integers(40, 150))
            cv2.rectangle(img, (x, y), (x + rw, y + rh), (g + 5, g + 1, g - 3), -1)
        horizon = self.margin_y + self.height // 2 + int(rng.integers(-40, 40))
        cv2.rectangle(img, (0, horizon), (w, h), (58, 56, 52), -1)
        for gx in range(0, w, 64):
            cv2.line(img, (gx, horizon), (gx, h), (70, 68, 64), 1)
        noise = rng.normal(0, 9, (h, w, 1)).astype(np.float32)
        img = cv2.GaussianBlur(img + noise, (0, 0), 1.2)
        return np.clip(img, 0, 255).astype(np.uint8)

    # -- projection ------------------------------------------------------
    def project(self, yaw: float, pitch: float, view_yaw: float, view_pitch: float) -> tuple[float, float]:
        x = self.width / 2.0 + self.focal * math.tan(math.radians(yaw - view_yaw))
        y = self.height / 2.0 - self.focal * math.tan(math.radians(pitch - view_pitch))
        return x, y

    # -- rendering -------------------------------------------------------
    def render(self, spec: FrameSpec) -> tuple[np.ndarray, GroundTruth]:
        ox = int(round(self.margin_x + spec.view_yaw * self.deg_px))
        oy = int(round(self.margin_y - spec.view_pitch * self.deg_px))
        ox = min(max(ox, 0), self.pano.shape[1] - self.width)
        oy = min(max(oy, 0), self.pano.shape[0] - self.height)
        img = self.pano[oy:oy + self.height, ox:ox + self.width].copy()
        color_rgb = hex_rgb(self.profile["targets"]["colors"][spec.target_color])
        color = (color_rgb[2], color_rgb[1], color_rgb[0])
        truths: list[TargetTruth] = []
        cover_rects = []
        for c in spec.covers:
            x0, y0 = self.project(c.yaw0, c.pitch1, spec.view_yaw, spec.view_pitch)
            x1, y1 = self.project(c.yaw1, c.pitch0, spec.view_yaw, spec.view_pitch)
            cover_rects.append((x0, y0, x1, y1, c.shade))
        for t in spec.targets:
            if not t.visible:
                continue
            hx, hy = self.project(t.yaw, t.pitch, spec.view_yaw, spec.view_pitch)
            r = self.focal * 0.12 / t.dist_m
            bbox = self._draw_humanoid(img, hx, hy, r, color)
            occluded = any(x0 <= hx <= x1 and y0 <= hy <= y1 for x0, y0, x1, y1, _ in cover_rects)
            truths.append(TargetTruth(t.tid, (hx, hy), r, not occluded, bbox))
        for x0, y0, x1, y1, shade in cover_rects:
            cv2.rectangle(img, (int(round(x0)), int(round(y0))), (int(round(x1)), int(round(y1))),
                          (shade + 4, shade + 2, shade - 2), -1)
            cv2.rectangle(img, (int(round(x0)), int(round(y0))), (int(round(x1)), int(round(y1))),
                          (shade - 20, shade - 20, shade - 22), 2)
        if spec.draw_hud or spec.draw_fiducial:
            self._draw_hud(img, spec)
        cx = self.width / 2.0 + spec.crosshair_offset[0]
        cy = self.height / 2.0 + spec.crosshair_offset[1]
        if spec.draw_crosshair:
            self._draw_crosshair(img, int(round(cx)), int(round(cy)), spec.crosshair_gap, spec.crosshair_color)
        rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
        gt = GroundTruth(spec.t_ms, self.width, self.height, (cx, cy), truths, (spec.view_yaw, spec.view_pitch),
                         spec.moving, spec.ammo if spec.draw_hud else None, spec.timer if spec.draw_hud else None,
                         spec.shots, spec.drill if spec.draw_hud else None, dict(spec.meta))
        return rgba, gt

    def _draw_humanoid(self, img: np.ndarray, x: float, y: float, r: float, color) -> tuple[float, float, float, float]:
        f = float(1 << 4)  # 4-bit fixed point for sub-pixel anti-aliased drawing

        def P(px: float, py: float) -> tuple[int, int]:
            return int(round(px * f)), int(round(py * f))

        shoulders = y + 1.35 * r
        waist = y + 5.5 * r
        torso = np.array([P(x - 1.9 * r, shoulders), P(x + 1.9 * r, shoulders),
                          P(x + 1.5 * r, waist), P(x - 1.5 * r, waist)], dtype=np.int32)
        cv2.fillConvexPoly(img, torso, color, cv2.LINE_AA, 4)
        neck = np.array([P(x - 0.45 * r, y + 0.6 * r), P(x + 0.45 * r, y + 0.6 * r),
                         P(x + 0.45 * r, shoulders + 0.2 * r), P(x - 0.45 * r, shoulders + 0.2 * r)], dtype=np.int32)
        cv2.fillConvexPoly(img, neck, color, cv2.LINE_AA, 4)
        for side in (-1, 1):
            lx = x + side * 0.75 * r
            leg = np.array([P(lx - 0.6 * r, waist - 0.2 * r), P(lx + 0.6 * r, waist - 0.2 * r),
                            P(lx + 0.5 * r, y + 11.5 * r), P(lx - 0.5 * r, y + 11.5 * r)], dtype=np.int32)
            cv2.fillConvexPoly(img, leg, color, cv2.LINE_AA, 4)
        cv2.circle(img, P(x, y), int(round(r * f)), color, -1, cv2.LINE_AA, 4)
        return (x - 1.9 * r, y - r, 3.8 * r, 12.5 * r)

    def _draw_crosshair(self, img: np.ndarray, cx: int, cy: int, gap: float, color_rgb) -> None:
        color = (color_rgb[2], color_rgb[1], color_rgb[0])
        g = int(round(gap))
        L, t = 7, 2
        arms = [
            (cx - g - L, cy - t // 2, cx - g, cy + t - t // 2),
            (cx + g, cy - t // 2, cx + g + L, cy + t - t // 2),
            (cx - t // 2, cy - g - L, cx + t - t // 2, cy - g),
            (cx - t // 2, cy + g, cx + t - t // 2, cy + g + L),
        ]
        for x0, y0, x1, y1 in arms:
            cv2.rectangle(img, (x0 - 1, y0 - 1), (x1, y1), (0, 0, 0), -1)
        for x0, y0, x1, y1 in arms:
            cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), color, -1)

    def _draw_hud(self, img: np.ndarray, spec: FrameSpec) -> None:
        fid = self.profile["fiducial"]
        hud = self.profile["hud"]
        M = max(float(fid["size_css_px"]), float(fid["size_viewport_fraction"]) * self.height)
        margin = float(fid["margin_css_px"])
        frame = hud["fiducial_frame"]
        ox = margin - frame[0] * M
        oy = self.height - margin - (frame[1] + frame[3]) * M

        def rect(u0: float, v0: float, w: float, h: float, color_hex: str) -> None:
            r, g, b = hex_rgb(color_hex)
            x0, y0 = ox + u0 * M, oy + v0 * M
            cv2.rectangle(img, (int(round(x0)), int(round(y0))),
                          (int(round(x0 + w * M)) - 1, int(round(y0 + h * M)) - 1), (b, g, r), -1)

        colors = hud["colors"]
        if spec.draw_fiducial:
            rect(frame[0], frame[1], frame[2], frame[3], colors["frame"])
            qz = hud["quiet_zone"]
            rect(qz[0], qz[1], qz[2], qz[3], colors["quiet"])
            cells = int(fid["cells"])
            cell = 1.0 / cells
            for j, row in enumerate(fid["bits"]):
                for i, bit in enumerate(row):
                    rect(i * cell, j * cell, cell, cell, "#ffffff" if bit else "#000000")
        if spec.draw_hud:
            p = hud["panel"]
            rect(p[0], p[1], p[2], p[3], colors["panel"])
            values = {"ammo": spec.ammo, "timer": spec.timer, "drill": spec.drill}
            for name, ro in hud["readouts"].items():
                value = values.get(name)
                digits = int(ro["digits"])
                text = "" if value is None else str(max(0, value)).zfill(digits)[-digits:]
                for k in range(digits):
                    lit = set(hud["digit_patterns"][text[k]]) if text else set()
                    u0 = float(ro["x"]) + k * float(ro["pitch"])
                    for seg, (x0, y0, x1, y1) in hud["segments"].items():
                        col = colors["lit"] if seg in lit else colors["unlit"]
                        rect(u0 + x0 * ro["digit_w"], float(ro["y"]) + y0 * ro["digit_h"],
                             (x1 - x0) * ro["digit_w"], (y1 - y0) * ro["digit_h"], col)


def analysis_size(w: int, h: int, target_height: int = 540, max_width: int = 1280) -> tuple[int, int]:
    """Analysis ('full' region) size: scale to a fixed height, capped in width; never upscale.

    Mirrors apps/desktop/src/renderer/src/capture/regions.ts.
    """
    scale = min(1.0, target_height / h, max_width / w)
    return max(1, int(round(w * scale))), max(1, int(round(h * scale)))


def build_packet(rgba: np.ndarray, frame_id: int, ts_ms: float, session_id: str = "synthetic",
                 center_size: int = 384, simulated: bool = True, source_kind: str = "synthetic") -> bytes:
    """Encode a frame the same way the desktop capture pipeline does."""
    h, w = rgba.shape[:2]
    fw, fh = analysis_size(w, h)
    full = cv2.resize(rgba, (fw, fh), interpolation=cv2.INTER_AREA) if fw != w else rgba
    cs = min(center_size, w, h)
    cx0, cy0 = (w - cs) // 2, (h - cs) // 2
    center = np.ascontiguousarray(rgba[cy0:cy0 + cs, cx0:cx0 + cs])
    header = FramePacketHeader(
        session_id=session_id, frame_id=frame_id, source_id="synthetic:0", source_kind=source_kind,  # type: ignore[arg-type]
        source_label="TARI synthetic scene", acquired_ts_ms=ts_ms, sent_ts_ms=ts_ms,
        source_width=w, source_height=h, simulated=simulated,
        regions=[
            FrameRegion(name="full", src_rect=PixelRect(x=0, y=0, w=w, h=h), width=fw, height=fh,
                        byte_offset=0, byte_length=fw * fh * 4),
            FrameRegion(name="center", src_rect=PixelRect(x=cx0, y=cy0, w=cs, h=cs), width=cs, height=cs,
                        byte_offset=0, byte_length=cs * cs * 4),
        ],
    )
    return encode_frame_packet(header, {"full": np.ascontiguousarray(full).tobytes(), "center": center.tobytes()})
