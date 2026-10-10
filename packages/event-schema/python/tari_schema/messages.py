"""Stream protocol messages (JSON text frames) between desktop and engine."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from .coaching import CoachingRecommendation, Evidence
from .common import Domain, Priority, TariModel, VersionedModel
from .events import CoachingEvent
from .frame import SourceKind
from .overlay import OverlayInstruction
from .perception import ModuleStatus, PerceptionResult
from .settings import CoachingSettings, PerceptionSettings
from .state import GameState
from .telemetry import PerformanceSnapshot
from .voice import VoiceInstruction


# ---- client -> engine ----------------------------------------------------

class ClientSourceInfo(TariModel):
    source_id: str = Field(max_length=256)
    source_kind: SourceKind
    label: str = Field(default="", max_length=256)


class StartSessionMessage(VersionedModel):
    type: Literal["start_session"] = "start_session"
    session_id: str | None = Field(default=None, max_length=64)
    player_id: str = Field(default="local", max_length=64)
    source: ClientSourceInfo
    coaching: CoachingSettings = Field(default_factory=CoachingSettings)
    perception: PerceptionSettings = Field(default_factory=PerceptionSettings)


class UpdateSettingsMessage(VersionedModel):
    type: Literal["update_settings"] = "update_settings"
    coaching: CoachingSettings | None = None
    perception: PerceptionSettings | None = None


class EndSessionMessage(VersionedModel):
    type: Literal["end_session"] = "end_session"
    reason: str = "user_stopped"


class ClientMetricsMessage(VersionedModel):
    type: Literal["client_metrics"] = "client_metrics"
    snapshot: PerformanceSnapshot


class PingMessage(VersionedModel):
    type: Literal["ping"] = "ping"
    client_ts_ms: float


ClientMessage = Annotated[
    Union[StartSessionMessage, UpdateSettingsMessage, EndSessionMessage, ClientMetricsMessage, PingMessage],
    Field(discriminator="type"),
]


# ---- engine -> client ----------------------------------------------------

class EngineCapabilities(TariModel):
    perception_modules: list[ModuleStatus]
    onnx_providers_available: list[str]
    accelerator: str = Field(description="Execution provider used for neural models, or 'none' if no model loaded")
    coaching_domains_live: list[Domain]
    coaching_domains_planned: list[Domain]
    hud_profiles: list[str]
    riot_integration: Literal["disabled_pending_authorization"]


class HelloMessage(VersionedModel):
    type: Literal["hello"] = "hello"
    engine_version: str
    capabilities: EngineCapabilities


class SessionStartedMessage(VersionedModel):
    type: Literal["session_started"] = "session_started"
    session_id: str
    started_ts_ms: float
    persistence: Literal["sqlite", "unavailable"]


class FrameResultMessage(VersionedModel):
    type: Literal["frame_result"] = "frame_result"
    perception: PerceptionResult
    state: GameState
    events: list[CoachingEvent] = Field(default_factory=list)
    recommendations: list[CoachingRecommendation] = Field(default_factory=list)
    overlays: list[OverlayInstruction] = Field(default_factory=list)
    voice: list[VoiceInstruction] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class FrameDroppedMessage(VersionedModel):
    type: Literal["frame_dropped"] = "frame_dropped"
    frame_id: int | None
    reason: Literal["stale", "superseded", "invalid", "out_of_order", "no_session"]
    age_ms: float | None = None
    detail: str | None = None


class TelemetryMessage(VersionedModel):
    type: Literal["telemetry"] = "telemetry"
    snapshot: PerformanceSnapshot


class NoticeMessage(VersionedModel):
    type: Literal["notice"] = "notice"
    level: Literal["info", "warning", "error"]
    code: str
    message: str
    priority: Priority = "P2"


class SessionSummary(TariModel):
    session_id: str
    started_ts_ms: float
    ended_ts_ms: float
    frames_processed: int
    frames_dropped: int
    exposures: int
    acquisitions: int
    metrics: list[Evidence]


class SessionEndedMessage(VersionedModel):
    type: Literal["session_ended"] = "session_ended"
    session_id: str
    reason: str
    summary: SessionSummary


class PongMessage(VersionedModel):
    type: Literal["pong"] = "pong"
    client_ts_ms: float
    engine_ts_ms: float


EngineMessage = Annotated[
    Union[
        HelloMessage, SessionStartedMessage, FrameResultMessage, FrameDroppedMessage,
        TelemetryMessage, NoticeMessage, SessionEndedMessage, PongMessage,
    ],
    Field(discriminator="type"),
]
