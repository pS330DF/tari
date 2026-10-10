"""Overlay instructions: spatial annotations bound to one analyzed frame."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Point2, TariModel, VersionedModel

OverlayKind = Literal["box", "circle", "line", "arrow", "polyline", "hline", "text", "cross"]
OverlayStyle = Literal[
    "target", "head", "crosshair", "crosshair_estimated", "error", "correction",
    "trajectory", "guide", "label", "warning", "good",
]


class OverlayPrimitive(TariModel):
    kind: OverlayKind
    style: OverlayStyle
    points: list[Point2] = Field(default_factory=list)
    radius: float | None = Field(default=None, description="Normalized by source width")
    text: str | None = None
    emphasis: float = 1.0


class OverlayInstruction(VersionedModel):
    instruction_id: str
    session_id: str
    source_frame_id: int
    source_ts_ms: float = Field(description="Acquisition time of the frame these primitives describe")
    created_ts_ms: float
    ttl_ms: float = Field(description="Renderer must hide primitives once frame age exceeds this in live mode")
    layer: Literal["spatial", "panel"]
    gated_by: Literal["training_lab", "authorized"]
    primitives: list[OverlayPrimitive]
