"""TARI versioned event schema (v1). Source of truth for Python and TypeScript types."""

from .coaching import CoachingRecommendation, Evidence, Expiration
from .common import (
    PRIORITY_RANK, Domain, Language, ObservationStatus, PixelRect, Point2, Priority, Rect, TariModel, VersionedModel,
)
from .events import (
    CoachingEvent, EnvironmentChangedEvent, EventBase, FlickAnalyzedEvent, PerceptionNoticeEvent, ShotFiredEvent,
    SourceReconfiguredEvent, TargetAcquiredEvent, TargetExposedEvent, TargetLostEvent,
)
from .frame import (
    FRAME_MAGIC, FRAME_PACKET_VERSION, FramePacketError, FramePacketHeader, FrameRegion, decode_frame_packet,
    encode_frame_packet,
)
from .messages import (
    ClientMessage, ClientMetricsMessage, ClientSourceInfo, EndSessionMessage, EngineCapabilities, EngineMessage,
    FrameDroppedMessage, FrameResultMessage, HelloMessage, NoticeMessage, PingMessage, PongMessage,
    SessionEndedMessage, SessionStartedMessage, SessionSummary, StartSessionMessage, TelemetryMessage,
    UpdateSettingsMessage,
)
from .overlay import OverlayInstruction, OverlayPrimitive
from .perception import (
    CrosshairObservation, EgoMotion, EnvironmentObservation, HudReading, HudReadout, ModuleStatus, PerceptionResult,
    TargetDetection,
)
from .profile import PlayerProfile, RecurringIssue, SkillDataPoint, SkillProgress
from .settings import CoachingSettings, PerceptionSettings
from .state import (
    BoolField, EventSummary, FieldMeta, GameState, IntField, MotionField, PointField, TextField, TextListField,
    TrackState,
)
from .telemetry import LatencyStats, PerformanceMetric, PerformanceSnapshot
from .voice import VoiceInstruction
from .version import SCHEMA_MAJOR, SCHEMA_VERSION, is_compatible

# Model names exported to JSON Schema / TypeScript.
EXPORTED_MODELS = [
    FramePacketHeader, FrameRegion, PerceptionResult, GameState, CoachingRecommendation, OverlayInstruction,
    VoiceInstruction,
    PlayerProfile, PerformanceMetric, PerformanceSnapshot, CoachingSettings, PerceptionSettings,
    StartSessionMessage, UpdateSettingsMessage, EndSessionMessage, ClientMetricsMessage, PingMessage,
    HelloMessage, SessionStartedMessage, FrameResultMessage, FrameDroppedMessage, TelemetryMessage,
    NoticeMessage, SessionEndedMessage, PongMessage,
    TargetExposedEvent, TargetAcquiredEvent, TargetLostEvent, FlickAnalyzedEvent, ShotFiredEvent,
    EnvironmentChangedEvent, SourceReconfiguredEvent, PerceptionNoticeEvent,
]
