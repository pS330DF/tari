"""Per-frame perception output. Every field is an observation of *this* frame.

Modules that fail report ``state="failed"`` with a reason and contribute no
data; nothing is back-filled or fabricated.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Point2, Rect, TariModel, VersionedModel

ModuleState = Literal["ok", "degraded", "failed", "skipped", "unavailable"]


class ModuleStatus(TariModel):
    name: str
    state: ModuleState
    backend: str | None = None
    duration_ms: float | None = None
    detail: str | None = None


class CrosshairObservation(TariModel):
    position: Point2
    method: Literal["detected", "assumed_center"]
    confidence: float = Field(ge=0, le=1)
    arm_gap_px: float | None = Field(default=None, description="Center-to-inner-arm distance, source px")
    arms_found: int = 0


class TargetDetection(TariModel):
    bbox: Rect
    head: Point2
    head_radius: float = Field(description="Head radius normalized by source width")
    head_method: Literal["head_profile", "top_ratio", "blob_top", "refined_crop"]
    confidence: float = Field(ge=0, le=1)
    area_px: int = Field(description="Approximate silhouette area in source px")
    backend: str
    crosshair_overlap: bool = Field(default=False, description="Head partly covered by the crosshair (position less certain)")


class EgoMotion(TariModel):
    """Global image motion between the previous and current analyzed frames.

    Rotation and player translation are not separated: this is *view* motion.
    """

    shift_px: Point2 = Field(description="Content displacement prev->cur, source px")
    view_rate_dps: Point2 = Field(description="Estimated view angular velocity: x=yaw (+right), y=pitch (+up)")
    interval_ms: float
    response: float
    confidence: float = Field(ge=0, le=1)
    measurable: bool


class HudReadout(TariModel):
    name: str
    value: int | None
    raw: str | None = None
    confidence: float = Field(ge=0, le=1)


class HudReading(TariModel):
    profile: str
    readouts: list[HudReadout]


class EnvironmentObservation(TariModel):
    kind: Literal["training_lab", "unknown"]
    marker_id: int | None = None
    map_id: str | None = None
    corners: list[Point2] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class PerceptionResult(VersionedModel):
    session_id: str
    frame_id: int
    acquired_ts_ms: float
    engine_received_ts_ms: float
    processing_started_ts_ms: float
    processed_ts_ms: float
    source_width: int
    source_height: int
    simulated: bool = False
    crosshair: CrosshairObservation | None = None
    targets: list[TargetDetection] = Field(default_factory=list)
    ego_motion: EgoMotion | None = None
    hud: HudReading | None = None
    environment: EnvironmentObservation | None = None
    modules: list[ModuleStatus] = Field(default_factory=list)
