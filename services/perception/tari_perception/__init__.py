"""TARI perception: local, deterministic computer vision over captured frames."""

from .crosshair import CrosshairAnalyzer
from .egomotion import EgoMotionEstimator
from .fiducial import FiducialDetector
from .frames import FrameView, RegionView
from .geometry import Projection
from .hud import SevenSegmentHudParser
from .kb import load_environment_profile
from .pipeline import PerceptionPipeline
from .targets import ColorTargetDetector, estimate_head

__all__ = [
    "ColorTargetDetector", "CrosshairAnalyzer", "EgoMotionEstimator", "FiducialDetector", "FrameView",
    "PerceptionPipeline", "Projection", "RegionView", "SevenSegmentHudParser", "estimate_head",
    "load_environment_profile",
]
