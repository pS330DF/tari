"""Builds spatial overlay instructions bound to the analyzed frame.

Primitives use normalized source-frame coordinates. Every instruction carries
the source frame id/timestamp and a TTL; renderers must hide it once stale.
"""

from __future__ import annotations

import math
import uuid

from tari_schema import GameState, OverlayInstruction, OverlayPrimitive, Point2

from .aim import FeedbackFlash
from .phrasing import Phraser

OVERLAY_TTL_MS = 200.0
TRAIL_MS = 800.0


def _pt(x: float, y: float) -> Point2:
    return Point2(x=round(x, 5), y=round(y, 5))


class OverlayBuilder:
    def __init__(self, phraser: Phraser):
        self.phraser = phraser

    def build(self, state: GameState, flashes: dict[int, FeedbackFlash], density: str, hfov_deg: float,
              source_size: tuple[int, int], trails: dict[int, list[tuple[float, float, float]]],
              created_ts_ms: float) -> OverlayInstruction:
        W, H = source_size
        f = (W / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        prims: list[OverlayPrimitive] = []
        cross = state.crosshair
        cpos = cross.value
        if cpos is not None and cross.status in ("observed", "estimated"):
            style = "crosshair" if cross.status == "observed" else "crosshair_estimated"
            prims.append(OverlayPrimitive(kind="cross", style=style, points=[cpos], radius=14.0 / W))
            if cross.status == "estimated":
                prims.append(OverlayPrimitive(kind="text", style="warning", points=[_pt(cpos.x + 0.012, cpos.y + 0.025)],
                                              text=self.phraser.flash("assumed")))
        detailed = density == "detailed"
        standard = density in ("standard", "detailed")
        for t in state.targets:
            if t.status != "visible":
                continue
            b = t.bbox
            if standard:
                prims.append(OverlayPrimitive(kind="box", style="target",
                                              points=[_pt(b.x, b.y), _pt(b.x + b.w, b.y + b.h)]))
                prims.append(OverlayPrimitive(kind="hline", style="guide",
                                              points=[_pt(b.x - 0.6 * b.w, t.head.y), _pt(b.x + 1.6 * b.w, t.head.y)]))
            prims.append(OverlayPrimitive(kind="circle", style="head", points=[t.head], radius=t.head_radius))
            if cpos is not None and cross.status == "observed" and t.error_deg is not None and t.head_radius_deg:
                mag = math.hypot(t.error_deg.x, t.error_deg.y)
                if mag > t.head_radius_deg:
                    prims.append(OverlayPrimitive(kind="arrow", style="correction", points=[cpos, t.head]))
                    if standard:
                        mid = _pt((cpos.x + t.head.x) / 2 + 0.006, (cpos.y + t.head.y) / 2)
                        arrow = "↑" if t.error_deg.y > 0 else "↓"
                        prims.append(OverlayPrimitive(kind="text", style="label", points=[mid],
                                                      text=f"{arrow} {abs(t.error_deg.y):.1f}°  ↔ {abs(t.error_deg.x):.1f}°"))
            if detailed and t.track_id in trails:
                pts = []
                hx, hy = t.head.x * W, t.head.y * H
                last_ts = trails[t.track_id][-1][0] if trails[t.track_id] else 0.0
                for ts, ex, ey in trails[t.track_id]:
                    if last_ts - ts > TRAIL_MS:
                        continue
                    x = hx - f * math.tan(math.radians(ex))
                    y = hy + f * math.tan(math.radians(ey))
                    pts.append(_pt(x / W, y / H))
                if len(pts) >= 2:
                    prims.append(OverlayPrimitive(kind="polyline", style="trajectory", points=pts))
            flash = flashes.get(t.track_id)
            if flash is not None:
                prims.append(OverlayPrimitive(kind="text", style=flash.style,  # type: ignore[arg-type]
                                              points=[_pt(b.x + b.w + 0.008, t.head.y - 0.01)], text=flash.text))
        return OverlayInstruction(
            instruction_id=uuid.uuid4().hex[:16], session_id=state.session_id, source_frame_id=state.frame_id,
            source_ts_ms=state.ts_ms, created_ts_ms=created_ts_ms, ttl_ms=OVERLAY_TTL_MS, layer="spatial",
            gated_by="training_lab" if state.coaching_mode == "live_training" else "authorized", primitives=prims,
        )
