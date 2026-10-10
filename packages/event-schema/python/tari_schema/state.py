"""Temporal game state: the engine's continuously updated belief.

Every field states *how* it is known: observed this frame, estimated from
other observations, stale (last observation too old), or unknown.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import ObservationStatus, Point2, Rect, TariModel, VersionedModel
from .perception import EgoMotion


class FieldMeta(TariModel):
    status: ObservationStatus = "unknown"
    confidence: float = Field(default=0.0, ge=0, le=1)
    updated_ts_ms: float | None = None
    source: str | None = None
    method: str | None = None
    reason: str | None = Field(default=None, description="Why the field is unknown/stale, if it is")


class TextField(FieldMeta):
    value: str | None = None


class IntField(FieldMeta):
    value: int | None = None


class BoolField(FieldMeta):
    value: bool | None = None


class PointField(FieldMeta):
    value: Point2 | None = None


class MotionField(FieldMeta):
    value: EgoMotion | None = None


class TextListField(FieldMeta):
    value: list[str] | None = None


class TrackState(TariModel):
    track_id: int
    status: Literal["visible", "coasting"]
    head: Point2
    head_radius: float
    bbox: Rect
    confidence: float
    first_seen_ts_ms: float
    last_seen_ts_ms: float
    error_deg: Point2 | None = Field(
        default=None, description="Head minus crosshair in degrees: x>0 head right of crosshair, y>0 head above"
    )
    head_radius_deg: float | None = None
    acquired: bool = False
    acquisition_ms: float | None = None


class EventSummary(TariModel):
    event_id: str
    type: str
    ts_ms: float


CoachingMode = Literal["live_training", "live_authorized", "restricted"]


class GameState(VersionedModel):
    session_id: str
    frame_id: int
    ts_ms: float = Field(description="Acquisition time of the frame this state reflects")
    environment: TextField
    map: TextField
    agent: TextField
    abilities: TextListField
    round_phase: TextField
    drill: TextField = Field(default_factory=TextField, description="Training Lab drill read from the HUD")
    teammates: TextListField
    crosshair: PointField
    movement_error: BoolField
    view_motion: MotionField
    ammo: IntField
    timer_s: IntField
    targets: list[TrackState] = Field(default_factory=list)
    recent_events: list[EventSummary] = Field(default_factory=list)
    observation_confidence: float = Field(ge=0, le=1)
    coaching_mode: CoachingMode
    coaching_mode_reason: str
