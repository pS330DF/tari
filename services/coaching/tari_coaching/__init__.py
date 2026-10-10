"""TARI coaching: deterministic coaches, priority/confidence filtering, overlay and voice output."""

from .aim import AimCoach
from .filter import PriorityConfidenceFilter
from .orchestrator import LIVE_DOMAINS, PLANNED_DOMAINS, CoachingOrchestrator, CoachingOutput
from .overlay import OverlayBuilder
from .phrasing import Phraser
from .voice import VoiceBuilder

__all__ = [
    "AimCoach", "CoachingOrchestrator", "CoachingOutput", "LIVE_DOMAINS", "OverlayBuilder", "PLANNED_DOMAINS",
    "Phraser", "PriorityConfidenceFilter", "VoiceBuilder",
]
