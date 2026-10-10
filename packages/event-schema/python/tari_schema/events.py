"""Typed coaching events produced by the temporal event-generation engine.

All ``ts_ms`` values are *source-frame acquisition times*, so measured
durations are not distorted by processing delay. Angular values use the
convention: x>0 = head right of crosshair, y>0 = head above crosshair.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from .common import Point2, VersionedModel


class EventBase(VersionedModel):
    event_id: str
    session_id: str
    frame_id: int
    ts_ms: float
    confidence: float = Field(ge=0, le=1)


class TargetExposedEvent(EventBase):
    type: Literal["target_exposed"] = "target_exposed"
    track_id: int
    head: Point2
    entry_error_deg: Point2
    head_radius_deg: float
    view_speed_dps: float | None
    view_settled: bool | None = Field(description="View speed below settle threshold at exposure (pre-aim held)")


class TargetAcquiredEvent(EventBase):
    type: Literal["target_acquired"] = "target_acquired"
    track_id: int
    acquisition_ms: float
    resolution_ms: float = Field(description="Timing uncertainty: interval between analyzed frames")
    entry_error_deg: Point2


class TargetLostEvent(EventBase):
    type: Literal["target_lost"] = "target_lost"
    track_id: int
    visible_ms: float
    acquired: bool


class FlickAnalyzedEvent(EventBase):
    type: Literal["flick_analyzed"] = "flick_analyzed"
    track_id: int
    outcome: Literal["clean", "overshoot", "undershoot", "unresolved"]
    initial_error_deg: float
    overshoot_deg: float | None = None
    residual_deg: float | None = Field(default=None, description="Error remaining when the first movement stopped")
    submovements: int
    inferred_view_frames: int = Field(
        default=0, description="Frames where view motion was unmeasurable and was inferred from the error change")


class ShotFiredEvent(EventBase):
    type: Literal["shot_fired"] = "shot_fired"
    shots: int
    track_id: int | None = None
    error_deg: Point2 | None = None
    on_head: bool | None = None
    view_speed_dps: float | None = None
    movement_error: bool | None = None


class EnvironmentChangedEvent(EventBase):
    type: Literal["environment_changed"] = "environment_changed"
    previous: str
    current: str
    coaching_mode: str


class SourceReconfiguredEvent(EventBase):
    type: Literal["source_reconfigured"] = "source_reconfigured"
    reason: Literal["session_start", "resolution_changed", "capture_gap"]
    width: int
    height: int
    gap_ms: float | None = None


class PerceptionNoticeEvent(EventBase):
    type: Literal["perception_notice"] = "perception_notice"
    module: str
    state: str
    message: str


CoachingEvent = Annotated[
    Union[
        TargetExposedEvent,
        TargetAcquiredEvent,
        TargetLostEvent,
        FlickAnalyzedEvent,
        ShotFiredEvent,
        EnvironmentChangedEvent,
        SourceReconfiguredEvent,
        PerceptionNoticeEvent,
    ],
    Field(discriminator="type"),
]
